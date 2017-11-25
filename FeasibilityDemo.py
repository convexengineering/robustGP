import numpy as np
from gpkit import Variable, Model
from Robust import RobustModel
from plot_feasibilities import plot_feasibilities

k = Variable("k", 1.17, "-", "form factor")
e = Variable("e", 0.92, "-", "Oswald efficiency factor")
mu = Variable("\\mu", 1.775e-5, "kg/m/s", "viscosity of air")
# pi = Variable("\\pi", np.pi, "-", "half of the circle constant", pr= 0)
rho = Variable("\\rho", 1.23, "kg/m^3", "density of air")
tau = Variable("\\tau", 0.12, "-", "airfoil thickness to chord ratio")
N_ult = Variable("N_{ult}", 3.3, "-", "ultimate load factor")
V_min = Variable("V_{min}", 25, "m/s", "takeoff speed")
C_Lmax = Variable("C_{L,max}", 1.6, "-", "max CL with flaps down")
S_wetratio = Variable("(\\frac{S}{S_{wet}})", 2.075, "-", "wetted area ratio")
W_W_coeff1 = Variable("W_{W_{coeff1}}", 12e-5, "1/m",
                      "Wing Weight Coefficent 1")
W_W_coeff2 = Variable("W_{W_{coeff2}}", 60, "Pa",
                      "Wing Weight Coefficent 2")
CDA0 = Variable("(CDA0)", 0.035, "m^2", "fuselage drag area")
W_0 = Variable("W_0", 6250, "N", "aircraft weight excluding wing")
toz = Variable("toz", 1, "-")

# Free Variables
D = Variable("D", "N", "total drag force")
A = Variable("A", "-", "aspect ratio")
S = Variable("S", "m^2", "total wing area")
V = Variable("V", "m/s", "cruising speed")
W = Variable("W", "N", "total aircraft weight")
Re = Variable("Re", "-", "Reynold's number")
C_D = Variable("C_D", "-", "Drag coefficient of wing")
C_L = Variable("C_L", "-", "Lift coefficent of wing")
C_f = Variable("C_f", "-", "skin friction coefficient")
W_w = Variable("W_w", "N", "wing weight")

constraints = []

# Drag model
C_D_fuse = CDA0 / S
C_D_wpar = k * C_f * S_wetratio
C_D_ind = C_L ** 2 / (np.pi * A * e)
constraints += [C_D >= C_D_fuse / toz + C_D_wpar / toz + C_D_ind / toz]

# Wing weight model
# W_w_strc = W_W_coeff1 * (N_ult * A ** 1.5 * (W_0 * W * S) ** 0.5) / tau
W_w_strc = W_W_coeff1 * (N_ult * A ** 1.5 * (W_0 * W * S) ** 0.5) / tau
W_w_surf = W_W_coeff2 * S
constraints += [W_w >= W_w_surf + W_w_strc]

# and the rest of the models
constraints += [D >= 0.5 * rho * S * C_D * V ** 2,
                Re <= (rho / mu) * V * (S / A) ** 0.5,
                C_f >= 0.074 / Re ** 0.2,
                W <= 0.5 * rho * S * C_L * V ** 2,
                W <= 0.5 * rho * S * C_Lmax * V_min ** 2,
                W >= W_0 + W_w]

m = Model(D, constraints)
m.solve()
plot_feasibilities(W_W_coeff1, W_W_coeff2, m)
# plot_feasibilities(k, W_W_coeff2, m)
W_W_coeff1.key.descr["pr"] = 60
# k.key.descr["pr"] = 10
W_W_coeff2.key.descr["pr"] = 66
RM = RobustModel(m, 'elliptical', two_term=True, linearizationTolerance=1e-4)
RMsol = RM.robustsolve(verbosity=1, minNumOfLinearSections=20, maxNumOfLinearSections=40)
rm = RM.get_robust_model()
plot_feasibilities(W_W_coeff1, W_W_coeff2, m, rm, "elliptical")
# plot_feasibilities(k, W_W_coeff2, m, rm, "elliptical")