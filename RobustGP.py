import numpy as np
import EquivalentModels as EM
import EquivalentPosynomial as EP
from gpkit import  Model
from gpkit import Variable, Monomial, SignomialsEnabled
from sklearn import linear_model

class UncertainCoefficientsModel(equivalentModel):
    """
    Creates robust Models
    """
    def setup(self, gamma, type_of_uncertainty_set, r_min = 5, tol=0.001,
                 number_of_regression_points = 2, two_term = True,
                 linearize_two_term = True, enable_sp = True):
        """
        Constructs a robust model starting from a model with uncertain coefficients
        :param gamma: Controls the size of the uncertainty set
        :param type_of_uncertainty_set: box, elliptical, or one norm set
        :param r_min: The minimum number of PWL functions
        :param tol: Determines the accuracy of PWL
        :param number_of_regression_points: The number of points per dimension used to replace exponential uncertainty
        function by a linear function
        :param two_term: Solve the problem using two term decoupling rather than linear approximation of exponential
        uncertainties
        :param linearize_two_term: linearize two term functions rather than considering them large posynomials
        :param enable_sp: choose to solve an SP to get a better solution
        :return: The robust Model, The initial guess if the robust model is an SP, and the number of PWL functions used
        to approximate two term monomials
        """
        r = r_min
        error = 1
        sol = 0
        model_upper, model_lower = \
            self.robustModelFixedNumberOfPWLs(gamma, r,
                                               type_of_uncertainty_set, tol,
                                               number_of_regression_points, True,
                                               two_term, linearize_two_term, False)
        while r <= 20 and error > tol:
            flag = 0
            try:
                sol_upper = model_upper.solve(verbosity = 0)
                sol = sol_upper
            except:
                flag = 1
            try:
                sol_lower = model_lower.solve(verbosity = 0)
            except:
                r=21
                sol = self.solve(verbosity = 0)
                break
            
            if flag != 1:    
                try:
                    error = \
                    (sol_upper.get('cost').m -
                     sol_lower.get('cost').m)/(0.0 + sol_lower.get('cost').m)
                except:
                    error = (sol_upper.get('cost') -
                             sol_lower.get('cost'))/(0.0 + sol_lower.get('cost'))
            r += 1
            model_upper, model_lower = \
                self.robustModelFixedNumberOfPWLs(gamma, r,
                                             type_of_uncertainty_set, tol,
                                             number_of_regression_points, True,
                                             two_term, linearize_two_term, False)
            
        initial_guess = sol.get("variables")
        
        if enable_sp:
            model_upper, model_lower = \
                self.robustModelFixedNumberOfPWLs(r-1, type_of_uncertainty_set,
                                             tol, number_of_regression_points,
                                             True, False, linearize_two_term,
                                             True)
            subsVars = model_upper.substitutions.keys()
            
            for i in xrange(len(subsVars)):
                del initial_guess[subsVars[i].key]

        return model_upper, initial_guess, r


    @staticmethod
    def merge_mesh_grid(array,n):
        """

        :param array:
        :param n:
        :return:
        """
        if n == 1:
            return [array]
        else:
            output = []
            for i in xrange(len(array)):
                output = output + UncertainCoefficientsModel.merge_mesh_grid(array[i],n/(len(array) + 0.0))
            return output 


    @staticmethod
    def perturbationFunction(perturbationVector,numberOfPoints):
        dim = len(perturbationVector)
        if dim != 1:
            x = np.meshgrid(*[np.linspace(-1,1,numberOfPoints)]*dim)
        else:
            x = [np.linspace(-1,1,numberOfPoints)]
        result = []
        inputList = []
        for i in xrange(numberOfPoints**dim):
            inputList.append([])
        for i in xrange(dim):
            temp = x[i].mergeMeshGrid(numberOfPoints**dim)
            for j in xrange(numberOfPoints**dim):
                inputList[j].append(temp[j])
        for i in xrange(numberOfPoints**dim):
            output = 1
            for j in xrange(dim):
                if perturbationVector[j] != 0:
                    output = output*perturbationVector[j]**inputList[i][j]
            result.append(output)
        clf = linear_model.LinearRegression()
        clf.fit(inputList,result)
        return clf.coef_, clf.intercept_

    @staticmethod
    def linearizePurturbations (p, uncertainVars, numberOfPoints):
        pUncertainVars = [var for var in p.varkeys if var in uncertainVars]
        center = []
        scale = []
        meanVector = []
        coeff = []
        intercept = []
        for i in xrange(len(pUncertainVars)):
            pr = pUncertainVars[i].key.pr
            center.append(np.sqrt(1 - pr**2/10000.0))
            scale.append(0.5*np.log((1 + pr/100.0)/(1 - pr/100.0)))
        perturbationMatrix = []
        for i in xrange(len(p.exps)):
            perturbationMatrix.append([])
            monUncertainVars = [var for var in pUncertainVars if var in p.exps[i]]
            mean = 1
            for j,var in enumerate(pUncertainVars):
                if var.key in monUncertainVars:
                    mean = mean*center[j]**(p.exps[i].get(var.key))
            meanVector.append(mean)
            for j,var in enumerate(pUncertainVars):
                if var.key in monUncertainVars:
                    perturbationMatrix[i].append(np.exp(p.exps[i].get(var.key)*scale[j]))
                else:
                    perturbationMatrix[i].append(0)
                coeff.append([])
                intercept.append([])
                coeff[i],intercept[i] = perturbationMatrix[i].perturbationFunction(numberOfPoints)
        return coeff, intercept, meanVector

    @staticmethod
    def noCoefficientMonomials (p, uncertainVars):
        monomials = []
        for i in xrange(len(p.exps)):
            monomials.append(Monomial(p.exps[i],p.cs[i]))
        return monomials

    @staticmethod
    def safePosynomialEllipticalUncertainty(p, uncertainVars, m, enableSP = False, numberOfPoints = 4):
        perturbationMatrix, intercept, meanVector = linearizePurturbations (p, uncertainVars, numberOfPoints)
        pUncertainVars = [var for var in p.varkeys if var in uncertainVars]
        if not pUncertainVars:
            return [p <= 1]
        monomials = noCoefficientMonomials (p, uncertainVars)
        constraints = []
        s_main = Variable("s_%s"%(m))
        constraints = constraints + [sum([a*b for a,b in zip([a*b for a,b in zip(meanVector,intercept)],monomials)]) + s_main**0.5 <= 1]
        ss = []
        for i in xrange(len(perturbationMatrix[0])):
            positivePert = []
            negativePert = []
            positiveMonomials = []
            negativeMonomials = []
            s = Variable("s^%s_%s"%(i,m))
            ss.append(s)
            for j in xrange(len(perturbationMatrix)):
                if perturbationMatrix[j][i] > 0:
                    positivePert.append(meanVector[j]*perturbationMatrix[j][i])
                    positiveMonomials.append(monomials[j])
                elif perturbationMatrix[j][i] < 0:
                    negativePert.append(-meanVector[j]*perturbationMatrix[j][i])
                    negativeMonomials.append(monomials[j])
            if enableSP:
                with SignomialsEnabled():
                    constraints = constraints + [(sum([a*b for a,b in zip(positivePert,positiveMonomials)]) 
                                             - sum([a*b for a,b in zip(negativePert,negativeMonomials)]))**2 <= s]
            else:
                constraints = constraints + [sum([a*b for a,b in zip(positivePert,positiveMonomials)])**2
                                         + sum([a*b for a,b in zip(negativePert,negativeMonomials)])**2 <= s]
        constraints.append(sum(ss) <= s_main)
        return constraints

    
def safePosynomialBoxUncertainty(p, uncertainVars, m, enableSP = False, 
                                 numberOfPoints = 4):
    perturbationMatrix, intercept, meanVector = \
                linearizePurturbations (p, uncertainVars, numberOfPoints)
    pUncertainVars = [var for var in p.varkeys if var in uncertainVars]
    if not pUncertainVars:
        return [p <= 1]
    monomials = noCoefficientMonomials (p, uncertainVars)
    constraints = []
    s_main = Variable("s_%s"%(m))
    constraints = constraints + [sum([a*b for a,b in zip
                                      ([a*b for a,b in zip
                                        (meanVector,intercept)],monomials)]) +\
                                                              s_main <= 1]
    ss = []
    for i in xrange(len(perturbationMatrix[0])):
        positivePert = []
        negativePert = []
        positiveMonomials = []
        negativeMonomials = []
        s = Variable("s^%s_%s"%(i,m))
        ss.append(s)
        for j in xrange(len(perturbationMatrix)):
            if perturbationMatrix[j][i] > 0:
                positivePert.append(meanVector[j]*perturbationMatrix[j][i])
                positiveMonomials.append(monomials[j])
            elif perturbationMatrix[j][i] < 0:
                negativePert.append(-meanVector[j]*perturbationMatrix[j][i])
                negativeMonomials.append(monomials[j])
        if enableSP:
            with SignomialsEnabled():
                if negativePert and not positivePert:
                    constraints = constraints + [sum([a*b for a,b in zip(negativePert,negativeMonomials)])<= s]
                elif positivePert and not negativePert:
                    constraints = constraints + [sum([a*b for a,b in zip(positivePert,positiveMonomials)])<= s]
                else:
                    constraints = constraints + [sum([a*b for a,b in zip(positivePert,positiveMonomials)]) 
                                                 - sum([a*b for a,b in zip(negativePert,negativeMonomials)])<= s]
                    constraints = constraints + [sum([a*b for a,b in zip(negativePert,negativeMonomials)]) 
                                                 - sum([a*b for a,b in zip(positivePert,positiveMonomials)])<= s]
        else:
            if positivePert:
                constraints = constraints + [sum([a*b for a,b in zip(positivePert,positiveMonomials)]) <= s]
            if negativePert:
                constraints = constraints + [sum([a*b for a,b in zip(negativePert,negativeMonomials)]) <= s]
    constraints.append(sum(ss) <= s_main)
    return constraints


def safePosynomialRhombalUncertainty(p, uncertainVars, m, enableSP = False, numberOfPoints = 4):
    perturbationMatrix, intercept, meanVector = linearizePurturbations (p, uncertainVars, numberOfPoints)
    pUncertainVars = [var for var in p.varkeys if var in uncertainVars]
    if not pUncertainVars:
        return [p <= 1]
    monomials = noCoefficientMonomials (p, uncertainVars)
    constraints = []
    s = Variable("s_%s"%(m))
    constraints = constraints + [sum([a*b for a,b in zip([a*b for a,b in zip(meanVector,intercept)],monomials)]) + s <= 1]
    for i in xrange(len(perturbationMatrix[0])):
        positivePert = []
        negativePert = []
        positiveMonomials = []
        negativeMonomials = []
        for j in xrange(len(perturbationMatrix)):
            if perturbationMatrix[j][i] > 0:
                positivePert.append(meanVector[j]*perturbationMatrix[j][i])
                positiveMonomials.append(monomials[j])
            elif perturbationMatrix[j][i] < 0:
                negativePert.append(-meanVector[j]*perturbationMatrix[j][i])
                negativeMonomials.append(monomials[j])
        if enableSP:
            with SignomialsEnabled():
                if negativePert and not positivePert:
                    constraints = constraints + [sum([a*b for a,b in zip(negativePert,negativeMonomials)])<= s]
                elif positivePert and not negativePert:
                    constraints = constraints + [sum([a*b for a,b in zip(positivePert,positiveMonomials)])<= s]
                else:
                    constraints = constraints + [sum([a*b for a,b in zip(positivePert,positiveMonomials)]) 
                                                 - sum([a*b for a,b in zip(negativePert,negativeMonomials)])<= s]
                    constraints = constraints + [sum([a*b for a,b in zip(negativePert,negativeMonomials)]) 
                                                 - sum([a*b for a,b in zip(positivePert,positiveMonomials)])<= s]
        else:
            if positivePert:
                constraints = constraints + [sum([a*b for a,b in zip(positivePert,positiveMonomials)]) <= s]
            if negativePert:
                constraints = constraints + [sum([a*b for a,b in zip(negativePert,negativeMonomials)]) <= s]
    return constraints   
        
    def robustModelFixedNumberOfPWLs(model, Gamma, typeOfUncertaintySet, r, tol, 
                                     numberOfRegressionPoints, twoTerm = True, 
                                     linearizeTwoTerm = True, enableSP = True):
        
        if typeOfUncertaintySet == 'box':
            dependentUncertaintySet = False
        else:
            dependentUncertaintySet = True
        
        simplifiedModelUpper, simplifiedModelLower, numberOfNoDataConstraints \
            = EM.tractableModel(model, r, tol, dependentUncertaintySet =False, 
                                twoTerm, linearizeTwoTerm)
        
        noDataConstraintsUpper, noDataConstraintsLower = [],[]
        dataConstraints, dataMonomails = [],[]
        
        uncertainVars = uncertainModelVariables(model)
        posynomialsUpper = simplifiedModelUpper.as_posyslt1()
        posynomialsLower = simplifiedModelLower.as_posyslt1()
        
        for i,p in enumerate(posynomialsUpper):
            if i < numberOfNoDataConstraints:
                noDataConstraintsUpper = noDataConstraintsUpper + [p <= 1]
                noDataConstraintsLower = noDataConstraintsLower + \
                                                [posynomialsLower[i] <= 1]
            else:
                if len(p.exps) > 1:
                    dataConstraints.append(EP.safePosynomialBoxUncertainty
                                           (p, uncertainVars, i, enableSP, 
                                            numberOfRegressionPoints))
                else:
                    dataMonomails.append(p)

        expsOfUncertainVars = uncertainVariablesExponents (dataMonomails, 
                                                           uncertainVars)
        
        if expsOfUncertainVars.size > 0:
            centeringVector, scalingVector = \
            normalizePerturbationVector(uncertainVars)
            coefficient = \
            constructRobustMonomailCoefficients(expsOfUncertainVars, Gamma, 
                                                typeOfUncertaintySet, 
                                                centeringVector, scalingVector)
            for i in xrange(len(dataMonomails)):
                dataConstraints = dataConstraints + \
                                    [coefficient[i][0]*dataMonomails[i] <= 1]
        outputUpper = Model(model.cost, 
                            [noDataConstraintsUpper,dataConstraints])
        outputUpper.substitutions.update(model.substitutions) 
        outputLower = Model(model.cost, 
                            [noDataConstraintsLower,dataConstraints])
        outputLower.substitutions.update(model.substitutions) 
        return outputUpper, outputLower
        
        
    def uncertainVariablesExponents (dataMonomials, uncertainVars):
        RHS_Coeff_Uncertain = \
        np.array([[-p.exps[0].get(var.key, 0) for var in uncertainVars] 
                   for p in dataMonomials])
        return  RHS_Coeff_Uncertain
        

    def normalizePerturbationVector(uncertainVars):
        prs = np.array([var.key.pr for var in uncertainVars])
        etaMax = np.log(1 + prs/100.0)
        etaMin = np.log(1 - prs/100.0)
        centeringVector = (etaMin + etaMax)/2.0
        scalingVector = etaMax - centeringVector
        return centeringVector, scalingVector
        

    def constructRobustMonomailCoefficients(RHS_Coeff_Uncertain, Gamma,
                                            typeOfSet, centeringVector, 
                                            scalingVector):
        b_purt = (RHS_Coeff_Uncertain * scalingVector[np.newaxis])       
        coefficient = []
        for i in xrange(RHS_Coeff_Uncertain.shape[0]):
            norm = 0
            centering = 0
            for j in range(RHS_Coeff_Uncertain.shape[1]):
                if typeOfSet == 'box':
                    norm = norm + np.abs(b_purt[i][j])
                elif typeOfSet == 'elliptical':
                    norm = norm + b_purt[i][j]**2
                elif typeOfSet == 'one norm':
                    norm = max(norm,np.abs(b_purt[i][j]))
                else:
                    raise Exception('This type of set is not supported')
                centering = centering + RHS_Coeff_Uncertain[i][j] * \
                                                            centeringVector[j]
            if typeOfSet == 'elliptical':
                norm = np.sqrt(norm)
            coefficient.append([np.exp(Gamma*norm)/np.exp(centering)])
        return coefficient
        
    
def robustModelBoxUncertaintyUpperLower(model, Gamma,r,tol, 
                                        numberOfRegressionPoints = 4, 
                                        coupled = True, twoTerm = True, 
                                        linearizeTwoTerm = True, 
                                        enableSP = True):
    simplifiedModelUpper, simplifiedModelLower, numberOfNoDataConstraints = \
                EM.tractableModel(model,r,tol,coupled, False, twoTerm, 
                                  linearizeTwoTerm)
    noDataConstraintsUpper = []
    noDataConstraintsLower = []
    dataConstraints = []
    dataMonomails = []
    uncertainVars = EM.uncertainModelVariables(model)
    posynomialsUpper = simplifiedModelUpper.as_posyslt1()
    posynomialsLower = simplifiedModelLower.as_posyslt1()
    for i,p in enumerate(posynomialsUpper):
        #print(i)
        if i < numberOfNoDataConstraints:
            noDataConstraintsUpper = noDataConstraintsUpper + [p <= 1]
            noDataConstraintsLower = noDataConstraintsLower + \
                                            [posynomialsLower[i] <= 1]
        else:
            if len(p.exps) > 1:
                dataConstraints.append(EP.safePosynomialBoxUncertainty
                                       (p, uncertainVars, i, enableSP, 
                                        numberOfRegressionPoints))
            else:
                dataMonomails.append(p)
    uncertainVars = EM.uncertainModelVariables(model)
    expsOfUncertainVars = uncertainVariablesExponents (dataMonomails, 
                                                       uncertainVars)
    if expsOfUncertainVars.size > 0:
        centeringVector, scalingVector = \
                                normalizePerturbationVector(uncertainVars)
        coefficient = constructRobustMonomailCoefficients(expsOfUncertainVars, 
                                                          Gamma, 'box', 
                                                          centeringVector, 
                                                          scalingVector)
        for i in xrange(len(dataMonomails)):
            dataConstraints = dataConstraints + \
                                    [coefficient[i][0]*dataMonomails[i] <= 1]
    outputUpper = Model(model.cost, [noDataConstraintsUpper,dataConstraints])
    outputUpper.substitutions.update(model.substitutions) 
    outputLower = Model(model.cost, [noDataConstraintsLower,dataConstraints])
    outputLower.substitutions.update(model.substitutions) 
    return outputUpper, outputLower

def robustModelBoxUncertainty(model, Gamma, tol=0.001, 
                              numberOfRegressionPoints = 4, coupled = True, 
                              twoTerm = True, linearizeTwoTerm = True, 
                              enableSP = True):
    r = 2
    error = 1
    sol = 0
    flag = 0 
    while r <= 20 and error > 0.01:
        flag = 0
        #print(r)
        modelUpper, modelLower = \
            robustModelBoxUncertaintyUpperLower(model, Gamma,r,tol, 
                                                numberOfRegressionPoints, 
                                                coupled, twoTerm, 
                                                linearizeTwoTerm, False)
        try:
            solUpper = modelUpper.solve(verbosity = 0)
            sol = solUpper
        except:
            flag = 1
        try:
            solLower = modelLower.solve(verbosity = 0)
        except:
            print("infeasible")
            r=20
            sol = model.solve(verbosity = 0)
            break
        if flag != 1:    
            try:
                error = \
                    (solUpper.get('cost').m - 
                     solLower.get('cost').m)/(0.0 + solLower.get('cost').m)
            except:
                error = (solUpper.get('cost') - 
                         solLower.get('cost'))/(0.0 + solLower.get('cost'))
        r = r + 1
    initialGuess = sol.get("variables")
    if enableSP:
        modelUpper, modelLower = \
            robustModelBoxUncertaintyUpperLower(model,r-1,tol, 
                                                numberOfRegressionPoints, 
                                                coupled, False, 
                                                linearizeTwoTerm, True)
        subsVars = modelUpper.substitutions.keys()
        for i in xrange(len(subsVars)):
            del initialGuess[subsVars[i].key]
    return modelUpper, initialGuess, r
    
def robustModelEllipticalUncertaintyUpperLower(model, Gamma,r,tol, 
                                               numberOfRegressionPoints = 4, 
                                               coupled = True, 
                                               dependentUncertainties = True, 
                                               twoTerm = False, 
                                               linearizeTwoTerm = True, 
                                               enableSP = True):
    simplifiedModelUpper, simplifiedModelLower, numberOfNoDataConstraints = \
        EM.tractableModel(model,r,tol,coupled,dependentUncertainties, 
                          twoTerm, linearizeTwoTerm)
    noDataConstraintsUpper = []
    noDataConstraintsLower = []
    dataConstraints = []
    dataMonomails = []
    uncertainVars = EM.uncertainModelVariables(model)
    posynomialsUpper = simplifiedModelUpper.as_posyslt1()
    posynomialsLower = simplifiedModelLower.as_posyslt1()
    for i,p in enumerate(posynomialsUpper):
        if i < numberOfNoDataConstraints:
            noDataConstraintsUpper = noDataConstraintsUpper + [p <= 1]
            noDataConstraintsLower = noDataConstraintsLower + \
                                            [posynomialsLower[i] <= 1]
        else:
            if len(p.exps) > 1:
                dataConstraints.append(EP.safePosynomialEllipticalUncertainty
                                       (p, uncertainVars, i, enableSP, 
                                        numberOfRegressionPoints))
            else:
                dataMonomails.append(p)
    uncertainVars = EM.uncertainModelVariables(model)
    expsOfUncertainVars = uncertainVariablesExponents (dataMonomails, 
                                                       uncertainVars)
    if expsOfUncertainVars.size > 0:
        centeringVector, scalingVector = \
                                    normalizePerturbationVector(uncertainVars)
        coefficient = \
            constructRobustMonomailCoeffiecientsEllipticalUncertainty
            (expsOfUncertainVars, Gamma, centeringVector, scalingVector)
        for i in xrange(len(dataMonomails)):
            dataConstraints = dataConstraints + \
                                    [coefficient[i][0]*dataMonomails[i] <= 1]
    outputUpper = Model(model.cost, [noDataConstraintsUpper,dataConstraints])
    outputUpper.substitutions.update(model.substitutions) 
    outputLower = Model(model.cost, [noDataConstraintsLower,dataConstraints])
    outputLower.substitutions.update(model.substitutions) 
    return outputUpper, outputLower

def robustModelEllipticalUncertainty(model, Gamma, tol = 0.001, 
                                     numberOfRegressionPoints = 4 , 
                                     coupled = True, 
                                     dependentUncertainties = True, 
                                     twoTerm = False, linearizeTwoTerm = True, 
                                     enableSP = True):
    r = 2
    error = 1
    sol = 0
    flag = 0 
    while r <= 20 and error > 0.00001:
        flag = 0
        #print(r)
        #print(error)
        modelUpper, modelLower = \
            robustModelEllipticalUncertaintyUpperLower(model, Gamma, r, tol, 
                                                       numberOfRegressionPoints, 
                                                       coupled, 
                                                       dependentUncertainties, 
                                                       twoTerm, 
                                                       linearizeTwoTerm, False)
        try:
            solUpper = modelUpper.solve(verbosity = 0)
            sol = solUpper
        except:
            flag = 1
        try:
            solLower = modelLower.solve(verbosity = 0)
        except:
            print("infeasible")
            r=20
            sol = model.solve(verbosity = 0)
            break
        if flag != 1:
            try:
                error = \
                    (solUpper.get('cost').m - 
                     solLower.get('cost').m)/(0.0 + solLower.get('cost').m)
            except:
                error = (solUpper.get('cost') - 
                         solLower.get('cost'))/(0.0 + solLower.get('cost'))
        r = r + 1
    initialGuess = sol.get("variables")
    if enableSP:
        modelUpper, modelLower = \
            robustModelEllipticalUncertaintyUpperLower(model, r-1, tol, 
                                                       numberOfRegressionPoints, 
                                                       coupled, 
                                                       dependentUncertainties, 
                                                       False, linearizeTwoTerm, 
                                                       True)
        subsVars = modelUpper.substitutions.keys()
        for i in xrange(len(subsVars)):
            del initialGuess[subsVars[i].key]
    return modelUpper, initialGuess, r
    
def robustModelRhombalUncertaintyUpperLower(model,r,tol, 
                                            numberOfRegressionPoints = 4, 
                                            coupled = True, 
                                            dependentUncertainties = True, 
                                            twoTerm = True, 
                                            linearizeTwoTerm = True, 
                                            enableSP = True):
    simplifiedModelUpper, simplifiedModelLower, numberOfNoDataConstraints = \
        EM.tractableModel(model, r, tol, coupled, dependentUncertainties, 
                          twoTerm, linearizeTwoTerm)
    noDataConstraintsUpper = []
    noDataConstraintsLower = []
    dataConstraints = []
    dataMonomails = []
    uncertainVars = EM.uncertainModelVariables(model)
    posynomialsUpper = simplifiedModelUpper.as_posyslt1()
    posynomialsLower = simplifiedModelLower.as_posyslt1()
    for i,p in enumerate(posynomialsUpper):
        if i < numberOfNoDataConstraints:
            noDataConstraintsUpper = noDataConstraintsUpper + [p <= 1]
            noDataConstraintsLower = noDataConstraintsLower + \
                                            [posynomialsLower[i] <= 1]
        else:
            if len(p.exps) > 1:
                dataConstraints.append(EP.safePosynomialRhombalUncertainty
                                       (p, uncertainVars, i, enableSP))
            else:
                dataMonomails.append(p)
    uncertainVars = EM.uncertainModelVariables(model)
    expsOfUncertainVars = uncertainVariablesExponents (dataMonomails, 
                                                       uncertainVars)
    if expsOfUncertainVars.size > 0:
        centeringVector, scalingVector = \
                                    normalizePerturbationVector(uncertainVars)
        coefficient = \
            constructRobustMonomailCoeffiecientsRhombalUncertainty
            (expsOfUncertainVars, centeringVector, scalingVector)
        for i in xrange(len(dataMonomails)):
            dataConstraints = dataConstraints + \
                                    [coefficient[i][0]*dataMonomails[i] <= 1]
    outputUpper = Model(model.cost, [noDataConstraintsUpper,dataConstraints])
    outputUpper.substitutions.update(model.substitutions) 
    outputLower = Model(model.cost, [noDataConstraintsLower,dataConstraints])
    outputLower.substitutions.update(model.substitutions) 
    return outputUpper, outputLower

def robustModelRhombalUncertainty(model, tol=0.001, 
                                  numberOfRegressionPoints = 4, coupled = True, 
                                  dependentUncertainties = True, 
                                  twoTerm = True, linearizeTwoTerm = True, 
                                  enableSP = True):
    r = 2
    error = 1
    sol = 0
    flag = 0 
    while r <= 20 and error > 0.01:
        flag = 0
        print(r)
        print(error)
        modelUpper, modelLower = \
            robustModelRhombalUncertaintyUpperLower(model, r, tol, 
                                                    numberOfRegressionPoints, 
                                                    coupled, 
                                                    dependentUncertainties, 
                                                    twoTerm, linearizeTwoTerm, 
                                                    False)
        try:
            solUpper = modelUpper.solve(verbosity = 0)
            sol = solUpper
        except:
            flag = 1
        try:
            solLower = modelLower.solve(verbosity = 0)
        except:
            print("infeasible")
            r=20
            sol = model.solve(verbosity = 0)
            break
        if flag != 1:
            try:
                error = \
                    (solUpper.get('cost').m - 
                     solLower.get('cost').m)/(0.0 + solLower.get('cost').m)
            except:
                error = (solUpper.get('cost') - 
                         solLower.get('cost'))/(0.0 + solLower.get('cost'))
        r = r + 1
    initialGuess = sol.get("variables")
    if enableSP:
        modelUpper, modelLower = \
            robustModelRhombalUncertaintyUpperLower(model, r-1, tol, 
                                                    numberOfRegressionPoints, 
                                                    coupled, 
                                                    dependentUncertainties, 
                                                    False, linearizeTwoTerm, 
                                                    True)
        subsVars = modelUpper.substitutions.keys()
        for i in xrange(len(subsVars)):
            del initialGuess[subsVars[i].key]
    return modelUpper, initialGuess, r

def boydRobustModelBoxUncertaintyUpperLower(model,r=3,tol=0.001):
    tracModelUpper, tracModelLower, numberOfNoDataConstraints = \
                                        EM.tractableBoydModel(model,r,tol)
    noDataConstraintsUpper = []
    noDataConstraintsLower = []
    dataConstraints = []
    dataMonomails = []
    posynomialsUpper = tracModelUpper.as_posyslt1()
    posynomialsLower = tracModelLower.as_posyslt1()
    for i,p in enumerate(posynomialsUpper):
        if i < numberOfNoDataConstraints:
            noDataConstraintsUpper = noDataConstraintsUpper + [p <= 1]
            noDataConstraintsLower = noDataConstraintsLower + \
                                            [posynomialsLower[i] <= 1]
        else:
            dataMonomails.append(p)
    uncertainVars = EM.uncertainModelVariables(model)
    expsOfUncertainVars = uncertainVariablesExponents (dataMonomails, 
                                                       uncertainVars)
    if expsOfUncertainVars.size > 0:
        centeringVector, scalingVector = \
                            normalizePerturbationVector(uncertainVars)
        coefficient = \
            constructRobustMonomailCoeffiecientsBoxUncertainty
            (expsOfUncertainVars, centeringVector, scalingVector)
        for i in xrange(len(dataMonomails)):
            dataConstraints = dataConstraints + \
                                    [coefficient[i][0]*dataMonomails[i] <= 1]
    outputUpper = Model(model.cost, [noDataConstraintsUpper,dataConstraints])
    outputUpper.substitutions.update(model.substitutions) 
    outputLower = Model(model.cost, [noDataConstraintsLower,dataConstraints])
    outputLower.substitutions.update(model.substitutions) 
    return outputUpper, outputLower

def boydRobustModelBoxUncertainty(model, tol=0.001):
    r = 3
    error = 1
    while r <= 20 and error > 0.01:
        modelUpper, modelLower = boydRobustModelBoxUncertaintyUpperLower(model, 
                                                                         r, 
                                                                         tol)
        solUpper = modelUpper.solve(verbosity = 0)
        solLower = modelLower.solve(verbosity = 0)
        try:
            error = \
                (solUpper.get('cost').m - 
                 solLower.get('cost').m)/(0.0 + solLower.get('cost').m)
        except:
            error = (solUpper.get('cost') - 
                     solLower.get('cost'))/(0.0 + solLower.get('cost'))
        r = r + 1
    return modelUpper,r
    
def boydRobustModelEllipticalUncertaintyUpperLower(model,r=3,tol=0.001):
    tracModelUpper, tracModelLower, numberOfNoDataConstraints = \
                                        EM.tractableBoydModel(model,r,tol)
    noDataConstraintsUpper = []
    noDataConstraintsLower = []
    dataConstraints = []
    dataMonomails = []
    posynomialsUpper = tracModelUpper.as_posyslt1()
    posynomialsLower = tracModelLower.as_posyslt1()
    for i,p in enumerate(posynomialsUpper):
        if i < numberOfNoDataConstraints:
            noDataConstraintsUpper = noDataConstraintsUpper + [p <= 1]
            noDataConstraintsLower = noDataConstraintsLower + \
                                            [posynomialsLower[i] <= 1]
        else:
            dataMonomails.append(p)
    uncertainVars = EM.uncertainModelVariables(model)
    expsOfUncertainVars = uncertainVariablesExponents (dataMonomails, 
                                                       uncertainVars)
    if expsOfUncertainVars.size > 0:
        centeringVector, scalingVector = \
                                normalizePerturbationVector(uncertainVars)
        coefficient = \
            constructRobustMonomailCoeffiecientsEllipticalUncertainty
            (expsOfUncertainVars, centeringVector, scalingVector)
        for i in xrange(len(dataMonomails)):
            dataConstraints = dataConstraints + \
                                    [coefficient[i][0]*dataMonomails[i] <= 1]
    outputUpper = Model(model.cost, [noDataConstraintsUpper,dataConstraints])
    outputUpper.substitutions.update(model.substitutions) 
    outputLower = Model(model.cost, [noDataConstraintsLower,dataConstraints])
    outputLower.substitutions.update(model.substitutions) 
    return outputUpper, outputLower

def boydRobustModelEllipticalUncertainty(model, tol=0.001):
    r = 3
    error = 1
    while r <= 20 and error > 0.01:
        modelUpper, modelLower = \
                boydRobustModelEllipticalUncertaintyUpperLower(model,r,tol)
        solUpper = modelUpper.solve(verbosity = 0)
        solLower = modelLower.solve(verbosity = 0)
        try:
            error = \
                (solUpper.get('cost').m - 
                 solLower.get('cost').m)/(0.0 + solLower.get('cost').m)
        except:
            error = (solUpper.get('cost') - 
                     solLower.get('cost'))/(0.0 + solLower.get('cost'))
        r = r + 1
    return modelUpper,r   
    
def solveRobustSPBox(model,Gamma,relTol = 1e-5):
    initSol = model.localsolve(verbosity=0)
    initCost = initSol['cost']
    newCost = initCost*(1 + 2*relTol)
    while (np.abs(initCost - newCost)/initCost) > relTol:
        apprModel = Model(model.cost,model.as_gpconstr(initSol))
        robModel = robustModelBoxUncertainty(apprModel,Gamma)[0]
        sol = robModel.solve(verbosity=0)
        initSol = sol.get('variables')
        initCost = newCost
        newCost = sol['cost']
        print(newCost)
    return initSol
