.text

.align 2
.global skeleton_asm_abi_version
.type skeleton_asm_abi_version, %function
skeleton_asm_abi_version:
    mov w0, #1
    ret
.size skeleton_asm_abi_version, .-skeleton_asm_abi_version

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

.section .note.GNU-stack,"",@progbits
