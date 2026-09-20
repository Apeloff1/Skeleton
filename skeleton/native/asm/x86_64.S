.text

.p2align 4
.globl skeleton_asm_abi_version
.type skeleton_asm_abi_version, @function
skeleton_asm_abi_version:
    mov $3, %eax
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

.p2align 4
.globl skeleton_asm_dot_batch_f32
.type skeleton_asm_dot_batch_f32, @function
skeleton_asm_dot_batch_f32:
    test %rdx, %rdx
    je .Lbatch_done

    mov %rdx, %rax
    mov %rdi, %r9

.Lbatch_row:
    xorps %xmm0, %xmm0
    xorps %xmm3, %xmm3
    xorps %xmm4, %xmm4
    xorps %xmm5, %xmm5
    mov %r9, %rdi

    mov %rcx, %rdx
    shr $4, %rdx
    je .Lbatch_vec4_setup

.Lbatch_vec16:
    movups 0(%rdi), %xmm1
    movups 0(%rsi), %xmm2
    mulps %xmm2, %xmm1
    addps %xmm1, %xmm0

    movups 16(%rdi), %xmm1
    movups 16(%rsi), %xmm2
    mulps %xmm2, %xmm1
    addps %xmm1, %xmm3

    movups 32(%rdi), %xmm1
    movups 32(%rsi), %xmm2
    mulps %xmm2, %xmm1
    addps %xmm1, %xmm4

    movups 48(%rdi), %xmm1
    movups 48(%rsi), %xmm2
    mulps %xmm2, %xmm1
    addps %xmm1, %xmm5

    add $64, %rdi
    add $64, %rsi
    dec %rdx
    jne .Lbatch_vec16

    addps %xmm3, %xmm0
    addps %xmm4, %xmm0
    addps %xmm5, %xmm0

.Lbatch_vec4_setup:
    mov %rcx, %rdx
    shr $2, %rdx
    and $3, %rdx
    je .Lbatch_reduce

.Lbatch_vec4:
    movups (%rdi), %xmm1
    movups (%rsi), %xmm2
    mulps %xmm2, %xmm1
    addps %xmm1, %xmm0
    add $16, %rdi
    add $16, %rsi
    dec %rdx
    jne .Lbatch_vec4

.Lbatch_reduce:
    movaps %xmm0, %xmm1
    movhlps %xmm0, %xmm1
    addps %xmm1, %xmm0
    movaps %xmm0, %xmm1
    shufps $0x55, %xmm1, %xmm1
    addss %xmm1, %xmm0

    mov %rcx, %rdx
    and $3, %rdx
    je .Lbatch_store

.Lbatch_tail_loop:
    movss (%rdi), %xmm1
    mulss (%rsi), %xmm1
    addss %xmm1, %xmm0
    add $4, %rdi
    add $4, %rsi
    dec %rdx
    jne .Lbatch_tail_loop

.Lbatch_store:
    movss %xmm0, (%r8)
    add $4, %r8
    dec %rax
    jne .Lbatch_row

.Lbatch_done:
    ret
.size skeleton_asm_dot_batch_f32, .-skeleton_asm_dot_batch_f32

.p2align 4
.globl skeleton_asm_dot_matrix_f32
.type skeleton_asm_dot_matrix_f32, @function
skeleton_asm_dot_matrix_f32:
    test %rsi, %rsi
    je .Lmatrix_done

    push %r12
    mov %rsi, %rax

.Lmatrix_query:
    mov %rdx, %r10
    mov %rcx, %r11
    test %r11, %r11
    je .Lmatrix_next_query

.Lmatrix_row:
    xorps %xmm0, %xmm0
    mov %rdi, %rsi
    mov %r8, %r12
    shr $2, %r12
    je .Lmatrix_tail

.Lmatrix_vec:
    movups (%rsi), %xmm1
    movups (%r10), %xmm2
    mulps %xmm2, %xmm1
    addps %xmm1, %xmm0
    add $16, %rsi
    add $16, %r10
    dec %r12
    jne .Lmatrix_vec

    movaps %xmm0, %xmm1
    movhlps %xmm0, %xmm1
    addps %xmm1, %xmm0
    movaps %xmm0, %xmm1
    shufps $0x55, %xmm1, %xmm1
    addss %xmm1, %xmm0

.Lmatrix_tail:
    mov %r8, %r12
    and $3, %r12
    je .Lmatrix_store

.Lmatrix_tail_loop:
    movss (%rsi), %xmm1
    mulss (%r10), %xmm1
    addss %xmm1, %xmm0
    add $4, %rsi
    add $4, %r10
    dec %r12
    jne .Lmatrix_tail_loop

.Lmatrix_store:
    movss %xmm0, (%r9)
    add $4, %r9
    dec %r11
    jne .Lmatrix_row

.Lmatrix_next_query:
    lea (%rdi,%r8,4), %rdi
    dec %rax
    jne .Lmatrix_query

    pop %r12
.Lmatrix_done:
    ret
.size skeleton_asm_dot_matrix_f32, .-skeleton_asm_dot_matrix_f32

.section .note.GNU-stack,"",@progbits
