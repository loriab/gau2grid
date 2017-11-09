"""
The C generator for gau2grid collocation functions
"""

import os
from . import order
from . import RSH
from . import codegen

_grads = ["x", "y", "z"]
_hessians = ["xx", "xy", "xz", "yy", "yz", "zz"]


def generate_c_gau2grid(max_L, path=".", cart_order="row", inner_block=64):
    print(path)

    gg_header = codegen.CodeGen(cgen=True)
    gg_density = codegen.CodeGen(cgen=True)

    # Add general header comments
    for cgs in [gg_header, gg_density]:
        cgs.write("// This is an automtically generated file from ...")
        cgs.write("// Blah blah blah")
        cgs.blankline()

    # Add utility headers
    for cgs in [gg_density]:
        cgs.write("#include <math.h>")
        cgs.blankline()

    # Write out the phi builders
    for L in range(max_L + 1):
        sig = shell_c_generator(gg_density, L, grad=0, cart_order=cart_order, inner_block=inner_block)

        # Write out the header data
        gg_header.write(sig)
        gg_header.blankline()

    gg_header.repr(filename=os.path.join(path, "gau2grid.h"), clang_format=True)
    gg_density.repr(filename=os.path.join(path, "gau2grid_phi.c"), clang_format=True)


def shell_c_generator(cg, L, function_name="", grad=0, cart_order="row", inner_block=64):

    if function_name == "":
        function_name = "coll_%d_%d" % (L, grad)

    # Precompute temps
    ncart = int((L + 1) * (L + 2) / 2)
    nspherical = L * 2 + 1

    # Build function signature
    if grad == 0:
        func_sig = "size_t npoints, double* x, double* y, double* z, int nprim, double* coeffs, double* exponents, double* center, bool spherical, double* ret"
    else:
        raise KeyError("Grad larger than 2 is not yet implemented.")

    func_sig = "void %s(%s)" % (function_name, func_sig)
    cg.start_c_block(func_sig)
    cg.blankline()

    # Figure out spacing
    cg.write("// Sizing")
    cg.write("size_t nblocks = npoints / %d" % inner_block)
    cg.write("nblocks += (nblocks %% %d) ? 0 : 1" % inner_block)
    cg.write("size_t ncart = %d" % ncart)
    cg.write("size_t nspherical = %d" % nspherical)
    cg.write("size_t nout = spherical ? nspherical : ncart")
    cg.blankline()

    # Build temporaries
    cg.write("// Allocate temporaries")
    S_tmps = ["xc", "yz", "zc", "R2", "S0"]
    for tname in S_tmps:
        cg.write("double*  %s = new double[%d]" % (tname, inner_block))

    L_tmps = ["xc_pow", "yz_pow", "zc_pow"]
    for tname in L_tmps:
        cg.write("double*  %s = new double[%d]" % (tname, inner_block * (L)))

    inner_tmps = ["phi_tmp"]
    for tname in inner_tmps:
        cg.write("double*  %s = new double[%d]" % (tname, inner_block * ncart))
    cg.blankline()

    # Start outer loop
    cg.write("// Start outer block loop")
    cg.start_c_block("for (size_t block = 0; block < nblocks; block++)")
    cg.blankline()

    # Move data into inner buffers
    cg.blankline()
    cg.write("// Copy data into inner temps")
    cg.write("size_t start = block * %d" % inner_block)
    cg.write("size_t remain = ((start + %d) > npoints) ? (npoints - start) : %d" % (inner_block, inner_block))

    cg.start_c_block("for (size_t i = 0; i < remain; i++)")
    cg.write("xc[i] = x[start + i] - center[0]")
    cg.write("yc[i] = y[start + i] - center[1]")
    cg.write("zc[i] = z[start + i] - center[2]")
    cg.close_c_block()
    cg.blankline()

    # Start inner loop
    cg.write("// Start inner block loop")
    cg.start_c_block("for (size_t i = 0; i < %d; i++)" % inner_block)

    cg.blankline()
    cg.write("// Position temps")
    cg.write("R2[i] = xc[i] * xc[i] + yc[i] * yc[i] + zc[i] * zc[i]")
    cg.blankline()

    cg.blankline()
    cg.write("// Deriv tmps")
    cg.start_c_block("for (size_t n = 0; n < nprim; n++)")
    cg.write("double T1 = coeffs[n] * exp(-1.0 * exponents[n] * R2[i])")
    cg.write("S0[i] += T1")
    cg.close_c_block()
    cg.blankline()

    cg.blankline()
    cg.write("// Power tmps")
    cg.write("xc_pow[i] = xc[i]")
    cg.write("yc_pow[i] = yc[i]")
    cg.write("zc_pow[i] = zc[i]")

    for l in range(1, L):
        cg.write("xc_pow[%d + i] = xc[%d + i]" % (inner_block * l, inner_block * (l - 1)))
        cg.write("xc_pow[%d + i] = xc[%d + i]" % (inner_block * l, inner_block * (l - 1)))
        cg.write("xc_pow[%d + i] = xc[%d + i]" % (inner_block * l, inner_block * (l - 1)))
    cg.blankline()

    cg.write("// AM loops")
    cg.blankline()
    _c_am_build(cg, L, cart_order, grad, inner_block)

    cg.blankline()

    # End inner loop
    cg.close_c_block()

    # Move data into inner buffers
    cg.blankline()
    cg.write("// Copy data back into outer temps")
    cg.start_c_block("for (size_t n = 0; n < nout; n++)")
    cg.start_c_block("for (size_t i = 0; i < remain; i++)")
    cg.write("ret[start * nout + i] = phi_out[%d * n + i]" % (inner_block))
    cg.close_c_block()
    cg.close_c_block()
    cg.blankline()

    # End outer loop
    cg.close_c_block()

    cg.write("// Free temporaries")
    for tname in (S_tmps + L_tmps + inner_tmps):
        cg.write("delete[] %s" % tname)
    cg.blankline()

    cg.close_c_block()

    # return cg.repr()
    return func_sig


def _c_am_build(cg, L, cart_order, grad, shift):
    """
    Builds a unrolled angular momentum function
    """
    names = ["X", "Y", "Z"]

    # Generator
    for idx, l, m, n in order.cartesian_order_factory(L, cart_order):

        l = l + 2
        m = m + 2
        n = n + 2
        ld1 = l - 1
        ld2 = l - 2
        md1 = m - 1
        md2 = m - 2
        nd1 = n - 1
        nd2 = n - 2
        tmp_ret = []

        # Set grads back to zero
        x_grad, y_grad, z_grad = False, False, False

        name = "X" * ld2 + "Y" * md2 + "Z" * nd2
        if name == "":
            name = "0"

        # Density
        cg.write("// Density AM=%d Component=%s" % (L, name))

        cg.write(_build_xyz_pow("A", 1.0, l, m, n))
        cg.write("phi_tmp[%d + i] = S0 * A" % (idx * shift))

        if grad == 0: continue
        cg.write("// Gradient AM=%d Component=%s" % (L, name))

        # Gradient
        cg.write("output['PHI_X'][%d] = SX * A" % idx)
        cg.write("output['PHI_Y'][%d] = SY * A" % idx)
        cg.write("output['PHI_Z'][%d] = SZ * A" % idx)

        AX = _build_xyz_pow("AX", ld2, ld1, m, n)
        if AX is not None:
            x_grad = True
            cg.write(AX)
            cg.write("output['PHI_X'][%d] += S0 * AX" % idx)

        AY = _build_xyz_pow("AY", md2, l, md1, n)
        if AY is not None:
            y_grad = True
            cg.write(AY)
            cg.write("output['PHI_Y'][%d] += S0 * AY" % idx)

        AZ = _build_xyz_pow("AZ", nd2, l, m, nd1)
        if AZ is not None:
            z_grad = True
            cg.write(AZ)
            cg.write("output['PHI_Z'][%d] += S0 * AZ" % idx)

        # Hessian temporaries
        cg.write("// Hessian AM=%d Component=%s" % (L, name))
        if grad == 1: continue

        # S Hess
        # We will build S Hess, grad 1, grad 2, A Hess

        # XX
        cg.write("output['PHI_XX'][%d] = SXX * A" % idx)
        if x_grad:
            cg.write("output['PHI_XX'][%d] += SX * AX" % idx)
            cg.write("output['PHI_XX'][%d] += SX * AX" % idx)

        AXX = _build_xyz_pow("AXX", ld2 * (ld2 - 1), ld2, m, n)
        if AXX is not None:
            rhs = AXX.split(" = ")[-1]
            cg.write("output['PHI_XX'][%d] += %s * S0" % (idx, rhs))

        # YY
        cg.write("output['PHI_YY'][%d] = SYY * A" % idx)
        if y_grad:
            cg.write("output['PHI_YY'][%d] += SY * AY" % idx)
            cg.write("output['PHI_YY'][%d] += SY * AY" % idx)
        AYY = _build_xyz_pow("AYY", md2 * (md2 - 1), l, md2, n)
        if AYY is not None:
            rhs = AYY.split(" = ")[-1]
            cg.write("output['PHI_YY'][%d] += %s * S0" % (idx, rhs))

        # ZZ
        cg.write("output['PHI_ZZ'][%d] = SZZ * A" % idx)
        if z_grad:
            cg.write("output['PHI_ZZ'][%d] += SZ * AZ" % idx)
            cg.write("output['PHI_ZZ'][%d] += SZ * AZ" % idx)
        AZZ = _build_xyz_pow("AZZ", nd2 * (nd2 - 1), l, m, nd2)
        if AZZ is not None:
            rhs = AZZ.split(" = ")[-1]
            cg.write("output['PHI_ZZ'][%d] += %s * S0" % (idx, rhs))

        # XY
        cg.write("output['PHI_XY'][%d] = SXY * A" % idx)

        if y_grad:
            cg.write("output['PHI_XY'][%d] += SX * AY" % idx)
        if x_grad:
            cg.write("output['PHI_XY'][%d] += SY * AX" % idx)

        AXY = _build_xyz_pow("AXY", ld2 * md2, ld1, md1, n)
        if AXY is not None:
            rhs = AXY.split(" = ")[-1]
            cg.write("output['PHI_XY'][%d] += %s * S0" % (idx, rhs))

        # XZ
        cg.write("output['PHI_XZ'][%d] = SXZ * A" % idx)
        if z_grad:
            cg.write("output['PHI_XZ'][%d] += SX * AZ" % idx)
        if x_grad:
            cg.write("output['PHI_XZ'][%d] += SZ * AX" % idx)
        AXZ = _build_xyz_pow("AXZ", ld2 * nd2, ld1, m, nd1)
        if AXZ is not None:
            rhs = AXZ.split(" = ")[-1]
            cg.write("output['PHI_XZ'][%d] += %s * S0" % (idx, rhs))

        # YZ
        cg.write("output['PHI_YZ'][%d] = SYZ * A" % idx)
        if z_grad:
            cg.write("output['PHI_YZ'][%d] += SY * AZ" % idx)
        if y_grad:
            cg.write("output['PHI_YZ'][%d] += SZ * AY" % idx)
        AYZ = _build_xyz_pow("AYZ", md2 * nd2, l, md1, nd1)
        if AYZ is not None:
            # cg.write(AYZ)
            rhs = AYZ.split(" = ")[-1]
            cg.write("output['PHI_YZ'][%d] += %s * S0" % (idx, rhs))
        cg.dedent()

        idx += 1
        cg.write(" ")


def _build_xyz_pow(name, pref, l, m, n, shift=2):
    """
    Builds an individual row contraction line.

    name = pref * xc_pow[n] yc_pow[m] * zc_pow[n]
    """
    l = l - shift
    m = m - shift
    n = n - shift

    if (pref <= 0) or (l < 0) or (n < 0) or (m < 0):
        return None

    mul = " "
    if pref == 1:
        ret = name + " ="
    else:
        # Basically always an int
        ret = name + " = %2.1f" % float(pref)
        mul = " * "

    if l > 0:
        ret += mul + "xc_pow[%d]" % (l - 1)
        mul = " * "

    if m > 0:
        ret += mul + "yc_pow[%d]" % (m - 1)
        mul = " * "

    if n > 0:
        ret += mul + "zc_pow[%d]" % (n - 1)
        mul = " * "

    if mul == " ":
        ret += " 1"

    return ret


def generate_hello(path='.'):
    print(path)
    with open(path + '/hello.c', 'w') as fl:
        fl.write("""
/* Hello World program */

#include<stdio.h>

int main()
{
    printf("Hello World");
}
""")