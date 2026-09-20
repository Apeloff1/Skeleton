.text

.p2align 4
.globl skeleton_asm_abi_version
.type skeleton_asm_abi_version, @function
skeleton_asm_abi_version:
    mov $1, %eax
    ret
.size skeleton_asm_abi_version, .-skeleton_asm_abi_version

.p2align 4
.globl skeleton_asm_dot_f32
.type skeleton_asm_dot_f32, @function
skeleton_asm_dot_f32:
    xorps %xmm0, %xmm0
    test %rdx, %rdx
    je .Ldot_done

    mov %rdx, %rcx
    shr $2, %rcx
    je .Ldot_tail

.Ldot_vec:
    movups (%rdi), %xmm1
    movups (%rsi), %xmm2
    mulps %xmm2, %xmm1
    addps %xmm1, %xmm0
    add $16, %rdi
    add $16, %rsi
    dec %rcx
    jne .Ldot_vec

    movaps %xmm0, %xmm1
    movhlps %xmm0, %xmm1
    addps %xmm1, %xmm0
    movaps %xmm0, %xmm1
    shufps $0x55, %xmm1, %xmm1
    addss %xmm1, %xmm0

.Ldot_tail:
    and $3, %rdx
    je .Ldot_done

.Ldot_tail_loop:
    movss (%rdi), %xmm1
    mulss (%rsi), %xmm1
    addss %xmm1, %xmm0
    add $4, %rdi
    add $4, %rsi
    dec %rdx
    jne .Ldot_tail_loop

.Ldot_done:
    ret
.size skeleton_asm_dot_f32, .-skeleton_asm_dot_f32

.p2align 4
.globl skeleton_asm_l2_sq_f32
.type skeleton_asm_l2_sq_f32, @function
skeleton_asm_l2_sq_f32:
    xorps %xmm0, %xmm0
    test %rdx, %rdx
    je .Ll2_done

    mov %rdx, %rcx
    shr $2, %rcx
    je .Ll2_tail

.Ll2_vec:
    movups (%rdi), %xmm1
    movups (%rsi), %xmm2
    subps %xmm2, %xmm1
    mulps %xmm1, %xmm1
    addps %xmm1, %xmm0
    add $16, %rdi
    add $16, %rsi
    dec %rcx
    jne .Ll2_vec

    movaps %xmm0, %xmm1
    movhlps %xmm0, %xmm1
    addps %xmm1, %xmm0
    movaps %xmm0, %xmm1
    shufps $0x55, %xmm1, %xmm1
    addss %xmm1, %xmm0

.Ll2_tail:
    and $3, %rdx
    je .Ll2_done

.Ll2_tail_loop:
    movss (%rdi), %xmm1
    subss (%rsi), %xmm1
    mulss %xmm1, %xmm1
    addss %xmm1, %xmm0
    add $4, %rdi
    add $4, %rsi
    dec %rdx
    jne .Ll2_tail_loop

.Ll2_done:
    ret
.size skeleton_asm_l2_sq_f32, .-skeleton_asm_l2_sq_f32

.section .note.GNU-stack,"",@progbits
