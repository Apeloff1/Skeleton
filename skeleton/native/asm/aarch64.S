.text

.align 2
.global skeleton_asm_abi_version
.type skeleton_asm_abi_version, %function
skeleton_asm_abi_version:
    mov w0, #4
    ret
.size skeleton_asm_abi_version, .-skeleton_asm_abi_version

.align 2
.global skeleton_asm_capabilities
.type skeleton_asm_capabilities, %function
skeleton_asm_capabilities:
    mov x0, #4
    ret
.size skeleton_asm_capabilities, .-skeleton_asm_capabilities

.align 2
.global skeleton_asm_dot_f32
.type skeleton_asm_dot_f32, %function
skeleton_asm_dot_f32:
    eor v0.16b, v0.16b, v0.16b
    cbz x2, .Ldot_done

    lsr x3, x2, #2
    cbz x3, .Ldot_tail

.Ldot_vec:
    ld1 {v1.4s}, [x0], #16
    ld1 {v2.4s}, [x1], #16
    fmla v0.4s, v1.4s, v2.4s
    subs x3, x3, #1
    b.ne .Ldot_vec

    faddp v0.4s, v0.4s, v0.4s
    faddp s0, v0.2s

.Ldot_tail:
    and x2, x2, #3
    cbz x2, .Ldot_done

.Ldot_tail_loop:
    ldr s1, [x0], #4
    ldr s2, [x1], #4
    fmadd s0, s1, s2, s0
    subs x2, x2, #1
    b.ne .Ldot_tail_loop

.Ldot_done:
    ret
.size skeleton_asm_dot_f32, .-skeleton_asm_dot_f32

.align 2
.global skeleton_asm_l2_sq_f32
.type skeleton_asm_l2_sq_f32, %function
skeleton_asm_l2_sq_f32:
    eor v0.16b, v0.16b, v0.16b
    cbz x2, .Ll2_done

    lsr x3, x2, #2
    cbz x3, .Ll2_tail

.Ll2_vec:
    ld1 {v1.4s}, [x0], #16
    ld1 {v2.4s}, [x1], #16
    fsub v3.4s, v1.4s, v2.4s
    fmla v0.4s, v3.4s, v3.4s
    subs x3, x3, #1
    b.ne .Ll2_vec

    faddp v0.4s, v0.4s, v0.4s
    faddp s0, v0.2s

.Ll2_tail:
    and x2, x2, #3
    cbz x2, .Ll2_done

.Ll2_tail_loop:
    ldr s1, [x0], #4
    ldr s2, [x1], #4
    fsub s3, s1, s2
    fmadd s0, s3, s3, s0
    subs x2, x2, #1
    b.ne .Ll2_tail_loop

.Ll2_done:
    ret
.size skeleton_asm_l2_sq_f32, .-skeleton_asm_l2_sq_f32

.align 2
.global skeleton_asm_dot_batch_f32
.type skeleton_asm_dot_batch_f32, %function
skeleton_asm_dot_batch_f32:
    cbz x2, .Lbatch_done

    mov x5, x2
    mov x6, x0

.Lbatch_row:
    eor v0.16b, v0.16b, v0.16b
    eor v4.16b, v4.16b, v4.16b
    eor v5.16b, v5.16b, v5.16b
    eor v6.16b, v6.16b, v6.16b
    mov x0, x6

    lsr x7, x3, #4
    cbz x7, .Lbatch_vec4_setup

.Lbatch_vec16:
    ld1 {v1.4s}, [x0], #16
    ld1 {v2.4s}, [x1], #16
    fmla v0.4s, v1.4s, v2.4s

    ld1 {v1.4s}, [x0], #16
    ld1 {v2.4s}, [x1], #16
    fmla v4.4s, v1.4s, v2.4s

    ld1 {v1.4s}, [x0], #16
    ld1 {v2.4s}, [x1], #16
    fmla v5.4s, v1.4s, v2.4s

    ld1 {v1.4s}, [x0], #16
    ld1 {v2.4s}, [x1], #16
    fmla v6.4s, v1.4s, v2.4s

    subs x7, x7, #1
    b.ne .Lbatch_vec16

    fadd v0.4s, v0.4s, v4.4s
    fadd v5.4s, v5.4s, v6.4s
    fadd v0.4s, v0.4s, v5.4s

.Lbatch_vec4_setup:
    lsr x7, x3, #2
    and x7, x7, #3
    cbz x7, .Lbatch_reduce

.Lbatch_vec4:
    ld1 {v1.4s}, [x0], #16
    ld1 {v2.4s}, [x1], #16
    fmla v0.4s, v1.4s, v2.4s
    subs x7, x7, #1
    b.ne .Lbatch_vec4

.Lbatch_reduce:
    faddp v0.4s, v0.4s, v0.4s
    faddp s0, v0.2s

    and x7, x3, #3
    cbz x7, .Lbatch_store

.Lbatch_tail_loop:
    ldr s1, [x0], #4
    ldr s2, [x1], #4
    fmadd s0, s1, s2, s0
    subs x7, x7, #1
    b.ne .Lbatch_tail_loop

.Lbatch_store:
    str s0, [x4], #4
    subs x5, x5, #1
    b.ne .Lbatch_row

.Lbatch_done:
    ret
.size skeleton_asm_dot_batch_f32, .-skeleton_asm_dot_batch_f32

.align 2
.global skeleton_asm_dot_matrix_f32
.type skeleton_asm_dot_matrix_f32, %function
skeleton_asm_dot_matrix_f32:
    cbz x1, .Lmatrix_done

    mov x6, x1

.Lmatrix_query:
    mov x7, x2
    mov x8, x3
    cbz x8, .Lmatrix_next_query

.Lmatrix_row:
    eor v0.16b, v0.16b, v0.16b
    eor v4.16b, v4.16b, v4.16b
    eor v5.16b, v5.16b, v5.16b
    eor v6.16b, v6.16b, v6.16b
    mov x9, x0

    lsr x10, x4, #4
    cbz x10, .Lmatrix_vec4_setup

.Lmatrix_vec16:
    ld1 {v1.4s}, [x9], #16
    ld1 {v2.4s}, [x7], #16
    fmla v0.4s, v1.4s, v2.4s

    ld1 {v1.4s}, [x9], #16
    ld1 {v2.4s}, [x7], #16
    fmla v4.4s, v1.4s, v2.4s

    ld1 {v1.4s}, [x9], #16
    ld1 {v2.4s}, [x7], #16
    fmla v5.4s, v1.4s, v2.4s

    ld1 {v1.4s}, [x9], #16
    ld1 {v2.4s}, [x7], #16
    fmla v6.4s, v1.4s, v2.4s

    subs x10, x10, #1
    b.ne .Lmatrix_vec16

    fadd v0.4s, v0.4s, v4.4s
    fadd v5.4s, v5.4s, v6.4s
    fadd v0.4s, v0.4s, v5.4s

.Lmatrix_vec4_setup:
    lsr x10, x4, #2
    and x10, x10, #3
    cbz x10, .Lmatrix_reduce

.Lmatrix_vec4:
    ld1 {v1.4s}, [x9], #16
    ld1 {v2.4s}, [x7], #16
    fmla v0.4s, v1.4s, v2.4s
    subs x10, x10, #1
    b.ne .Lmatrix_vec4

.Lmatrix_reduce:
    faddp v0.4s, v0.4s, v0.4s
    faddp s0, v0.2s

    and x10, x4, #3
    cbz x10, .Lmatrix_store

.Lmatrix_tail_loop:
    ldr s1, [x9], #4
    ldr s2, [x7], #4
    fmadd s0, s1, s2, s0
    subs x10, x10, #1
    b.ne .Lmatrix_tail_loop

.Lmatrix_store:
    str s0, [x5], #4
    subs x8, x8, #1
    b.ne .Lmatrix_row

.Lmatrix_next_query:
    add x0, x0, x4, lsl #2
    subs x6, x6, #1
    b.ne .Lmatrix_query

.Lmatrix_done:
    ret
.size skeleton_asm_dot_matrix_f32, .-skeleton_asm_dot_matrix_f32

.section .note.GNU-stack,"",@progbits
