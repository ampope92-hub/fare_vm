/* fvm_launch: run the built interpreter as the build user under a seccomp filter. It is root-only
   (mode 0700), started by root, and drops to the build user (uid and gid 10001) itself before the
   filter goes on, so the interpreter cannot run it again. The filter denies memfd_create, execveat
   and a few adjacent shared-memory calls with EPERM, and the calls that start a second process, so
   the job stays in the one program; everything else is allowed. Installed through prctl with
   no-new-privs set, and the process fails closed: if the uid drop or the filter does not take, it
   says why and exits without ever running the interpreter. */
#define _GNU_SOURCE
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <grp.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <linux/audit.h>
#include <linux/filter.h>
#include <linux/seccomp.h>

#ifndef SECCOMP_RET_KILL_PROCESS
#define SECCOMP_RET_KILL_PROCESS 0x80000000U
#endif

#ifndef __NR_clone3
#define __NR_clone3 435
#endif

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "fvm_launch: need a program to run\n");
        return 2;
    }

    struct sock_filter filter[] = {
        /* keep this to the architecture we built for; anything else is refused outright */
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, arch)),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, AUDIT_ARCH_X86_64, 1, 0),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS),
        /* load the syscall number */
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, nr)),
        /* the anonymous-executable route, and neighbours, all jump to the deny leaf, as do the
           calls that would start a second process: the work is the one program's to do, so a
           child worker is refused at the syscall rather than left to run beside it */
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, __NR_memfd_create, 9, 0),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, __NR_execveat,     8, 0),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, __NR_shmget,       7, 0),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, __NR_shmat,        6, 0),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, __NR_userfaultfd,  5, 0),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, __NR_clone,        4, 0),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, __NR_clone3,       3, 0),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, __NR_fork,         2, 0),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, __NR_vfork,        1, 0),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | (EPERM & SECCOMP_RET_DATA)),
    };
    struct sock_fprog prog = {
        .len = (unsigned short)(sizeof(filter) / sizeof(filter[0])),
        .filter = filter,
    };

    if (setgroups(0, NULL) != 0 || setgid(10001) != 0 || setuid(10001) != 0 || getuid() != 10001 || geteuid() != 10001) {
        fprintf(stderr, "fvm_launch: dropping to the build user failed: %s\n", strerror(errno));
        return 111;
    }
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0) {
        fprintf(stderr, "fvm_launch: PR_SET_NO_NEW_PRIVS failed: %s\n", strerror(errno));
        return 111;
    }
    if (prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &prog, 0, 0) != 0) {
        fprintf(stderr, "fvm_launch: seccomp filter install failed: %s\n", strerror(errno));
        return 111;
    }

    execv(argv[1], &argv[1]);
    fprintf(stderr, "fvm_launch: exec %s failed: %s\n", argv[1], strerror(errno));
    return 127;
}
