"""
MATHEMATICS COMPLETE DATABASE — From arithmetic to abstract algebra.
Full curriculum covering K-12 through PhD-level mathematics.
"""

def get_math_database():
    return {
        "fields": _get_math_fields(),
        "formulas": _get_key_formulas(),
        "theorems": _get_theorems(),
    }

def _get_math_fields():
    return [
        {"id":"math_arithmetic","name":"Arithmetic","level":"elementary","hours":200,"topics":["Addition/Subtraction","Multiplication/Division","Fractions","Decimals","Percentages","Order of Operations","Number Properties"]},
        {"id":"math_prealgebra","name":"Pre-Algebra","level":"middle","hours":200,"topics":["Variables","Expressions","Equations","Inequalities","Ratios","Proportions","Integers","Coordinate Plane"]},
        {"id":"math_algebra1","name":"Algebra I","level":"high_school","hours":300,"topics":["Linear Equations","Systems of Equations","Polynomials","Factoring","Quadratic Equations","Radical Expressions","Rational Expressions"]},
        {"id":"math_geometry","name":"Geometry","level":"high_school","hours":300,"topics":["Angles","Triangles","Circles","Area/Volume","Congruence","Similarity","Trigonometric Ratios","Proofs","Coordinate Geometry","Transformations"]},
        {"id":"math_algebra2","name":"Algebra II","level":"high_school","hours":300,"topics":["Complex Numbers","Logarithms","Exponentials","Sequences/Series","Conic Sections","Matrices","Probability"]},
        {"id":"math_precalculus","name":"Precalculus","level":"high_school","hours":300,"topics":["Functions","Trigonometry","Polar Coordinates","Vectors","Parametric Equations","Limits Introduction"]},
        {"id":"math_calculus1","name":"Calculus I","level":"university","hours":400,"topics":["Limits","Continuity","Derivatives","Chain Rule","Optimization","Related Rates","Mean Value Theorem","Integrals","FTC"]},
        {"id":"math_calculus2","name":"Calculus II","level":"university","hours":400,"topics":["Integration Techniques","Improper Integrals","Sequences","Series","Taylor/Maclaurin","Polar Integrals","Parametric Calculus"]},
        {"id":"math_calculus3","name":"Multivariable Calculus","level":"university","hours":400,"topics":["Partial Derivatives","Gradient","Divergence","Curl","Multiple Integrals","Line Integrals","Surface Integrals","Stokes Theorem","Divergence Theorem"]},
        {"id":"math_linear_algebra","name":"Linear Algebra","level":"university","hours":400,"topics":["Vectors","Matrices","Determinants","Eigenvalues/Eigenvectors","Vector Spaces","Linear Transformations","Inner Product Spaces","SVD","Jordan Form"]},
        {"id":"math_diff_eq","name":"Differential Equations","level":"university","hours":400,"topics":["First-Order ODEs","Second-Order ODEs","Laplace Transform","Systems of ODEs","Power Series Solutions","PDEs Introduction","Fourier Series"]},
        {"id":"math_discrete","name":"Discrete Mathematics","level":"university","hours":400,"topics":["Logic","Sets","Relations","Functions","Counting","Combinatorics","Graph Theory","Trees","Boolean Algebra","Recurrences","Generating Functions"]},
        {"id":"math_probability","name":"Probability & Statistics","level":"university","hours":400,"topics":["Probability Axioms","Conditional Probability","Bayes Theorem","Random Variables","Distributions","Expected Value","Variance","CLT","Hypothesis Testing","Regression","ANOVA","Bayesian Inference"]},
        {"id":"math_number_theory","name":"Number Theory","level":"university","hours":300,"topics":["Divisibility","Primes","GCD/LCM","Modular Arithmetic","Euler's Function","Fermat's Theorem","RSA Cryptography","Quadratic Residues","Continued Fractions"]},
        {"id":"math_real_analysis","name":"Real Analysis","level":"graduate","hours":500,"topics":["Sequences/Series","Topology of R","Continuity","Differentiability","Riemann Integration","Lebesgue Measure","Lebesgue Integration","Metric Spaces","Uniform Convergence"]},
        {"id":"math_complex_analysis","name":"Complex Analysis","level":"graduate","hours":400,"topics":["Complex Functions","Analytic Functions","Cauchy's Theorem","Laurent Series","Residue Theorem","Conformal Mappings","Riemann Surfaces"]},
        {"id":"math_abstract_algebra","name":"Abstract Algebra","level":"graduate","hours":500,"topics":["Groups","Rings","Fields","Homomorphisms","Quotient Groups","Sylow Theorems","Galois Theory","Module Theory","Category Theory Basics"]},
        {"id":"math_topology","name":"Topology","level":"graduate","hours":400,"topics":["Topological Spaces","Continuity","Connectedness","Compactness","Quotient Spaces","Fundamental Group","Covering Spaces","Homology"]},
        {"id":"math_numerical","name":"Numerical Methods","level":"university","hours":350,"topics":["Root Finding","Interpolation","Numerical Integration","ODE Solvers","Linear Systems","Eigenvalue Algorithms","FFT","Finite Elements","Error Analysis"]},
        {"id":"math_optimization","name":"Optimization","level":"graduate","hours":350,"topics":["Linear Programming","Simplex Method","Duality","Integer Programming","Convex Optimization","Gradient Descent","Newton's Method","Lagrange Multipliers","KKT Conditions"]},
        {"id":"math_graph_theory","name":"Graph Theory","level":"university","hours":300,"topics":["Graphs","Trees","Eulerian/Hamiltonian","Coloring","Planar Graphs","Network Flow","Matching","Ramsey Theory","Spectral Graph Theory"]},
        {"id":"math_crypto_math","name":"Cryptographic Mathematics","level":"graduate","hours":300,"topics":["Number Theory for Crypto","Elliptic Curves","Lattice-Based Crypto","Zero-Knowledge Proofs","Homomorphic Encryption","Post-Quantum Cryptography"]},
    ]

def _get_key_formulas():
    return [
        {"id":"f_quadratic","name":"Quadratic Formula","formula":"x = (-b ± √(b²-4ac)) / 2a","field":"algebra"},
        {"id":"f_pythagorean","name":"Pythagorean Theorem","formula":"a² + b² = c²","field":"geometry"},
        {"id":"f_euler","name":"Euler's Identity","formula":"e^(iπ) + 1 = 0","field":"complex_analysis"},
        {"id":"f_euler_formula","name":"Euler's Formula","formula":"e^(ix) = cos(x) + i·sin(x)","field":"complex_analysis"},
        {"id":"f_derivative","name":"Derivative Definition","formula":"f'(x) = lim(h→0) [f(x+h) - f(x)] / h","field":"calculus"},
        {"id":"f_ftc","name":"Fundamental Theorem of Calculus","formula":"∫[a,b] f(x)dx = F(b) - F(a)","field":"calculus"},
        {"id":"f_bayes","name":"Bayes' Theorem","formula":"P(A|B) = P(B|A)·P(A) / P(B)","field":"probability"},
        {"id":"f_normal","name":"Normal Distribution","formula":"f(x) = (1/σ√(2π)) · e^(-(x-μ)²/2σ²)","field":"statistics"},
        {"id":"f_binomial","name":"Binomial Theorem","formula":"(x+y)^n = Σ C(n,k)·x^(n-k)·y^k","field":"algebra"},
        {"id":"f_taylor","name":"Taylor Series","formula":"f(x) = Σ f^(n)(a)/n! · (x-a)^n","field":"calculus"},
        {"id":"f_stokes","name":"Stokes' Theorem","formula":"∮ F·dr = ∬ (∇×F)·dS","field":"vector_calculus"},
        {"id":"f_eigenvalue","name":"Eigenvalue Equation","formula":"Av = λv","field":"linear_algebra"},
        {"id":"f_det","name":"Determinant (2x2)","formula":"det(A) = ad - bc for [[a,b],[c,d]]","field":"linear_algebra"},
    ]

def _get_theorems():
    return [
        {"id":"t_ftc","name":"Fundamental Theorem of Calculus","field":"calculus","statement":"If F'(x)=f(x), then ∫[a,b]f(x)dx = F(b)-F(a)"},
        {"id":"t_clt","name":"Central Limit Theorem","field":"statistics","statement":"Sample means approach normal distribution as n→∞"},
        {"id":"t_ivt","name":"Intermediate Value Theorem","field":"analysis","statement":"Continuous f on [a,b] with f(a)<c<f(b) has f(x)=c for some x∈(a,b)"},
        {"id":"t_mvt","name":"Mean Value Theorem","field":"calculus","statement":"f'(c) = (f(b)-f(a))/(b-a) for some c∈(a,b)"},
        {"id":"t_cauchy","name":"Cauchy's Integral Theorem","field":"complex_analysis","statement":"∮ f(z)dz = 0 for analytic f on simply connected domain"},
        {"id":"t_lagrange","name":"Lagrange's Theorem","field":"algebra","statement":"Order of subgroup divides order of group"},
        {"id":"t_fermat","name":"Fermat's Little Theorem","field":"number_theory","statement":"a^p ≡ a (mod p) for prime p"},
        {"id":"t_noether","name":"Noether's Theorem","field":"physics","statement":"Every continuous symmetry has a corresponding conserved quantity"},
        {"id":"t_godel","name":"Gödel's Incompleteness","field":"logic","statement":"Any consistent formal system containing arithmetic has true unprovable statements"},
        {"id":"t_prime","name":"Prime Number Theorem","field":"number_theory","statement":"π(x) ~ x/ln(x) — primes thin out logarithmically"},
    ]
