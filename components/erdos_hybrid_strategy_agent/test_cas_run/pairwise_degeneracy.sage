# SageMath script: pairwise degeneracy for averaged product-fiber large sieve
# Run: sage pairwise_degeneracy.sage
R.<r,t,w,z,y> = PolynomialRing(QQ, 5, order='lex')
alpha = r - 1 + t - w
Lz = z*r + (z-12)*t - z*w
Ly = y*r + (y-12)*t - y*w
F1z = 4*Lz^2 + 4*(z+6)*Lz + z^2 - 60*z + 36
F1y = 4*Ly^2 + 4*(y+6)*Ly + y^2 - 60*y + 36
print('F1 degree in r:', F1z.degree(r))
print('disc_r(F1z) factor:')
print(factor(F1z.discriminant(r)))
Res = F1z.resultant(F1y, r)
print('resultant_r(F1z,F1y) factor:')
print(factor(Res))
print('squarefree decomposition of resultant:')
print(factor(Res.squarefree_part()))
if Res % ((y-z)^2) == 0:
    core = Res // ((y-z)^2)
else:
    core = Res
print('core after removing (y-z)^2 if divisible:')
print(factor(core))
print('STATUS: Sage F1 pairwise degeneracy script completed. Extend TODO for F2/F1F2.')
