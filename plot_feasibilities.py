import numpy as np
from gpkit import Model, Variable, ConstraintSet, GPCOLORS, GPBLU
from gpkit.small_scripts import mag

from RobustGPTools import RobustGPTools


def plot_feasibilities(x, y, m, rm=None):
    interesting_vars = [x, y]
    rmtype = None
    if rm:
        rmtype = rm.type_of_uncertainty_set

    # posynomials = m.as_posyslt1()
    # old = []
    # while set(old) != set(interesting_vars):
    #     old = interesting_vars
    #     for p in posynomials:
    #         if set([var.key.name for var in interesting_vars]) & set([var.key.name for var in p.varkeys.keys()]):
    #             interesting_vars = list(set(interesting_vars) | set([m[var.key.name] for var in p.varkeys.keys() if var.key.pr is not None]))

    class FeasCircle(Model):
        "SKIP VERIFICATION"

        def setup(self, m, sol, rob=False):
            r = 4
            additional_constraints = []
            slacks = []
            thetas = []
            for count in xrange((len(interesting_vars) - 1)):
                th = Variable("\\theta_%s" % count, np.linspace(0, 2 * np.pi, 360), "-")
                thetas += [th]
            for i_set in xrange(len(interesting_vars)):
                if rob:
                    eta_min_x, eta_max_x = RobustGPTools.generate_etas(interesting_vars[i_set], rmtype, rm.number_of_stds, rm.setting)
                else:
                    eta_min_x, eta_max_x = 0, 0
                center_x = (eta_min_x + eta_max_x) / 2.0
                xo = mag(m.solution(interesting_vars[i_set]))
                x_center = np.log(xo) + center_x

                def f(c, index=i_set, x_val=x_center):
                    product = 1
                    for j in xrange(index):
                        product *= np.cos(c[thetas[j]])
                    if index != len(interesting_vars) - 1:
                        product *= np.sin(c[thetas[index]])
                    return np.exp(x_val) * np.exp(r * product)
                if rmtype == 'box':
                    def g(c, index=i_set, x_val=x_center, x_nom=xo, eta=eta_max_x):
                        product = 1
                        for j in xrange(index):
                            product *= np.cos(c[thetas[j]])
                        if index != len(interesting_vars) - 1:
                            product *= np.sin(c[thetas[index]])
                        return np.exp(max(r*np.abs(product) - (np.log(x_nom) + eta - x_val), 0))
                else:
                    def g(c, index=i_set, x_val=x_center, x_nom=xo, eta=eta_max_x):
                        product = 1
                        for j in xrange(index):
                            product *= np.cos(c[thetas[j]])
                        if index != len(interesting_vars) - 1:
                            product *= np.sin(c[thetas[index]])
                        return np.exp(np.abs((np.log(x_nom) + eta - x_val - r)*product))

                x_i = Variable('x_%s' % i_set, f, interesting_vars[i_set].unitstr())
                s_i = Variable("s_%s" % i_set)
                slacks += [s_i]

                uncertaintyset = Variable('uncertaintyset_%s' % i_set, g)
                var = RobustGPTools.variables_bynameandmodels(m, interesting_vars[i_set].key.name,
                                                              interesting_vars[i_set].key.models)

                if len(var) > 1:
                    raise Exception("vector uncertain variables are not supported yet")
                else:
                    var = var[0]

                additional_constraints += [s_i >= 1, s_i <= uncertaintyset*1.0, var / s_i <= x_i, x_i <= var * s_i]

            cost_ref = Variable('cost_ref', 1, m.cost.unitstr(), "reference cost")
            self.cost = sum([sl ** 2 for sl in slacks]) * m.cost / cost_ref
            feas_slack = ConstraintSet(additional_constraints)
            return [m, feas_slack], {k: v for k, v in sol["freevariables"].items()
                                     if k in m.varkeys and k.key.fix is True}

    # plot original feasibility set
    # plot boundary of uncertainty set
    sol = None
    if rm:
        fc = FeasCircle(m, rm.get_robust_model().solution, rob=True)
        for interesting_var in interesting_vars:
            del fc.substitutions[interesting_var]
        sol = fc.solve(skipsweepfailures=True)
    ofc = FeasCircle(m, m.solution)
    for interesting_var in interesting_vars:
        del ofc.substitutions[interesting_var]
    origfeas = ofc.solve()
    from matplotlib import pyplot as plt
    fig, axes = plt.subplots(2)

    def plot_uncertainty_set(ax):
        xo, yo = map(mag, map(m.solution, [x, y]))
        ax.plot(xo, yo, "k.")
        if rm:
            eta_min_x, eta_max_x = RobustGPTools.generate_etas(x, rmtype, rm.number_of_stds, rm.setting)
            eta_min_y, eta_max_y = RobustGPTools.generate_etas(y, rmtype, rm.number_of_stds, rm.setting)
            center_x = (eta_min_x + eta_max_x) / 2.0
            center_y = (eta_min_y + eta_max_y) / 2.0
            x_center = np.log(xo) + center_x
            y_center = np.log(yo) + center_y
            ax.plot(np.exp(x_center), np.exp(y_center), "kx")
            if rmtype == "elliptical":
                th = np.linspace(0, 2 * np.pi, 50)
                ax.plot(np.exp(x_center) * np.exp(np.cos(th)) ** (np.log(xo) + eta_max_x - x_center),
                        np.exp(y_center) * np.exp(np.sin(th)) ** (np.log(yo) + eta_max_y - y_center), "k",
                        linewidth=1)
            elif rmtype:
                p = Polygon(
                    np.array([[xo * np.exp(eta_min_x)] + [xo * np.exp(eta_max_x)] * 2 + [xo * np.exp(eta_min_x)],
                              [yo * np.exp(eta_min_y)] * 2 + [yo * np.exp(eta_max_y)] * 2]).T,
                    True, edgecolor="black", facecolor="none", linestyle="dashed")
                ax.add_patch(p)

    orig_a, orig_b = map(mag, map(origfeas, [x, y]))
    a_i, b_i, a, b = [None] * 4
    if rm:
        x_index = interesting_vars.index(x)
        y_index = interesting_vars.index(y)

        a_i, b_i, a, b = map(mag, map(sol, ["x_%s" % x_index, "x_%s" % y_index, x, y]))

        for i in range(len(a)):
            axes[0].loglog([a_i[i], a[i]], [b_i[i], b[i]], color=GPCOLORS[1], linewidth=0.2)
    else:
        axes[0].loglog([orig_a[0]], [orig_b[0]], "k-")

    from matplotlib.patches import Polygon
    # from matplotlib.collections import PatchCollection

    perimeter = np.array([orig_a, orig_b]).T
    p = Polygon(perimeter, True, color=GPBLU, linewidth=0)
    axes[0].add_patch(p)
    if rm:
        perimeter = np.array([a, b]).T
        p = Polygon(perimeter, True, color=GPCOLORS[1], alpha=0.5, linewidth=0)
        axes[0].add_patch(p)
    plot_uncertainty_set(axes[0])
    axes[0].axis("equal")
    # axes[0].set_ylim([0.1, 1])
    axes[0].set_ylabel(y)

    perimeter = np.array([orig_a, orig_b]).T
    p = Polygon(perimeter, True, color=GPBLU, linewidth=0)
    axes[1].add_patch(p)
    if rm:
        perimeter = np.array([a, b]).T
        p = Polygon(perimeter, True, color=GPCOLORS[1], alpha=0.5, linewidth=0)
        axes[1].add_patch(p)
    plot_uncertainty_set(axes[1])
    # axes[1].set_xlim([0, 6])
    # axes[1].set_ylim([0, 1])
    axes[1].set_xlabel(x)
    axes[1].set_ylabel(y)

    fig.suptitle("%s vs %s feasibility space" % (x, y))
    plt.show()

