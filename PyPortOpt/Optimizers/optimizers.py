"""
The PortOpt application is powered by multiple optimizers designed to implement theory in an elegant 
and easy to use way.

This module consists all the functions required to run a portfolio optimization using parameters 
that the user inputs
"""
import math
import numpy as np
from numpy import linalg as LA
import pandas as pd
import osqp
import scipy as sp
from scipy import sparse


def testFunction():
    """
    Function to test if the import is working

    Parameters
    ----------
        This function has no parameters

    Returns
    ----------
        This function returns true
    """
    return True


def preprocessData(data):
    """
    Helper function to create a covariance matrix and mean vector

    Parameters
    ----------
    data : Dictionary
        Dictionary containing Date, Ticker and Adjusted Close price

    Returns
    -------
    meanVec : Vector
    sigMat : Matrix
    """
    data = pd.DataFrame.from_dict(data)
    df = data[["Date", "Ticker", "Adjusted_Close"]]
    df.columns = ["date", "ticker", "price"]
    df1 = df.pivot_table(index=["date"], columns="ticker", values=["price"])
    df1.columns = [col[1] for col in df1.columns.values]
    df_logret = 100 * (np.log(df1) - np.log(df1.shift(1)))
    df_logret = df_logret[1:]
    logret = np.array(df_logret)

    df_daily_returns = df1.pct_change()

    df_daily_returns = df_daily_returns[1:]
    data = np.array(data)
    daily_returns = np.array(df_daily_returns)
    n = logret.shape[0]
    sigMat = np.cov(logret, rowvar=False)
    meanVec = np.mean(logret, axis=0)
    return meanVec, sigMat


def SymPDcovmatrix(A, tol=None):
    """
    function corrects a covariance matrix A to be symmetric positive definite
    it uses eigenvalue decomposition and shifts all small eigenvalues to tol

    Parameters
    ----------
    A : Array like object
    tol : float
        (optional, default tol = 1e-04) minimum value for all eigenvalues

    Returns
    -------
    A : Array
        corrected matrix A.
    e_min : float
        minimum value for all eigenvalues
    """
    m, n = A.shape
    if n != m:
        print("Input matrix has to be a square matrix ")
    if not tol:
        tol = 1e-04
    A = (A + A.transpose()) / 2
    D, V = LA.eig(A)
    for i in range(len(D)):
        if D[i] < tol:
            D[i] = tol

    D = np.diag(D)
    t = np.dot(V, D)
    A = np.dot(t, V.transpose())
    e_min = max(tol, min(np.diag(D)))
    A = (A + A.transpose()) / 2
    return A, e_min


def sigMatShrinkage(sigMat, lambda_l2):
    """
    Function to shrink the covariance matrix

    Parameters
    ----------
    sigMat : Matrix
    lambda_l2 : Float

    Returns
    -------
    D : Array
    """
    d = sigMat.shape[0]
    sig = np.sqrt(np.diag(sigMat))
    t = np.dot(np.diag(sig ** (-1)), sigMat)
    corrMat = np.dot(t, np.diag(sig ** (-1)))
    corrs = None
    for k in range(d - 1):
        if corrs is None:
            corrs = np.diag(corrMat, k + 1)
        else:
            corrs = np.hstack([corrs, np.diag(corrMat, k + 1)])
    if 1 == 1:
        sigMat = sigMat + lambda_l2 * np.mean(sig ** 2) * np.eye(d)
    else:
        t = np.dot(
            np.mean(sig) * np.eye(d),
            np.eye(d) + (np.ones(d, d) - np.eye(d)) * np.mean(corrs),
        )
        sigMat = sigMat + lambda_l2 * np.dot(t, np.mean(sig) * np.eye(d))
    return sigMat


def Dmat(n, k):
    """
    function reform a matrix for assets with order

    Parameters
    ----------
    n : int
    k : int

    Returns
    -------
    D : Array
    """
    if k == 0:
        D = np.eye(n)
    elif k == 1:
        D = np.eye(n - 1, n)
        for i in range(n - 1):
            D[i, i + 1] = -1
    else:
        D = Dmat(n, 1)
        for i in range(k - 1):
            Dn = Dmat(n - i - 1, 1)
            D = np.dot(Dn, D)
    return D


def minimumVariancePortfolio(
    sigMat, longShort, maxAlloc=1, lambda_l1=0, lambda_l2=0, assetsOrder=None
):
    """
    Optimizes portfolio for minimum variance

    Parameters
    ----------
    SigMat : Matrix
    LongShort : Float
        Takes value between 0 and 1
    maxAlloc : Float
        Takes value between 0 and 1. Specifies the maximum weight an asset can get
    lambda_l1 : Float
        Takes a value greater than 0. Specifies L1 penalty
    lambda_l2 : Float
        Takes a value greater than 0. Specifies L2 penalty

    Returns
    -------
    w_opt : Array
        Returns the weights of given to each asset in form of a numpy array
    var_opt : Float
        Returns the variance of the portfolio
    """
    d = sigMat.shape[0]

    if assetsOrder:
        temp = sigMat[:, assetsOrder]
        sigMat = temp[assetsOrder, :]
    if lambda_l2:
        sigMat = sigMatShrinkage(sigMat, lambda_l2)
        sigMat, e_min = SymPDcovmatrix(sigMat)
    else:
        sigMat, e_min = SymPDcovmatrix(sigMat)

    if longShort == 0:
        Aeq = np.ones(d)
        Beq = 1
        LB = np.zeros(d)
        UB = maxAlloc * np.ones(d)
        if assetsOrder:
            L_ine = -np.ones(d - 1)
            D = np.eye(d - 1, d)
            for i in range(d - 1):
                D[i, i + 1] = -1
            A = -1 * D
            B = np.zeros(d - 1)
            A = np.vstack([A, Aeq, np.eye(d)])
            l = np.hstack([L_ine, Beq, LB])
            u = np.hstack([B, Beq, UB])
        else:
            A = np.vstack([Aeq, np.eye(d)])
            l = np.hstack([Beq, LB])
            u = np.hstack([Beq, UB])

        if lambda_l1:
            meanVec = -lambda_l1 * np.ones(d)
        else:
            meanVec = -np.zeros(d)

        P = sparse.csc_matrix(sigMat)
        A = sparse.csc_matrix(A)

        prob = osqp.OSQP()
        # Setup workspace
        prob.setup(P, -meanVec, A, l, u, verbose=False)
        # Solve problem
        res = prob.solve()
        w_opt = res.x
        if not w_opt.all():
            w_opt = np.ones(d) / d

    elif longShort != 0:
        A = np.hstack([np.zeros(d), np.ones(d), np.zeros(d)])
        B = 1 + abs(longShort)
        Grenze = min(abs(longShort), maxAlloc)
        if assetsOrder:
            L_ine = np.hstack([0, -(1 + 2 * Grenze) * np.ones(d - 1)])
            D = np.eye(d - 1, d)
            for i in range(d - 1):
                D[i, i + 1] = -1
            A = np.vstack([A, np.hstack([-1 * D, np.zeros((d - 1, 2 * d))])])
            B = np.hstack([B, np.zeros(d - 1)])
        else:
            L_ine = 0
        Aeq = np.vstack(
            [
                np.hstack([np.eye(d), -np.eye(d), np.eye(d)]),
                np.hstack([np.ones(d), np.zeros(d), np.zeros(d)]),
            ]
        )
        Beq = np.hstack([np.zeros(d), 1])
        LB = np.hstack([-Grenze * np.ones(d), np.zeros(2 * d)])
        UB = maxAlloc * np.ones(3 * d)
        sigMat3d = np.vstack(
            [np.hstack([sigMat, np.zeros((d, 2 * d))]), np.zeros((2 * d, 3 * d))]
        )

        sigMat3d = sigMat3d + np.diag(
            np.hstack([-0.1 * e_min * np.ones(d), 0.1 * e_min * np.ones(2 * d)])
        )

        if lambda_l1:
            meanvec3d = np.hstack([np.zeros(d), -lambda_l1 * np.ones(2 * d)])
        else:
            meanvec3d = np.hstack([np.zeros(d), np.zeros(2 * d)])

        A = np.vstack([A, Aeq, np.eye(3 * d)])
        l = np.hstack([L_ine, Beq, LB])
        u = np.hstack([B, Beq, UB])

        A = sparse.csc_matrix(A)
        sigMat3d = sparse.csc_matrix(sigMat3d)

        prob = osqp.OSQP()
        # Setup workspace
        prob.setup(sigMat3d, -meanvec3d, A, l, u, verbose=False)
        # Solve problem
        res = prob.solve()
        wuv_opt = res.x
        if not wuv_opt.all():
            w_opt = np.ones(d) / d
        else:
            w_opt = wuv_opt[:d]

    t = np.dot(w_opt, sigMat)
    Var_opt = np.dot(t, w_opt.transpose())
    if assetsOrder:
        w_opt = w_opt[assetsOrder]
    # if exitflag!=1:
    # print("minimumVariancePortfolio: Exitflag different than 1 in quadprog")
    return w_opt, Var_opt


def meanVariancePortfolioReturnsTarget(
    meanVec,
    sigMat,
    retTarget,
    longShort,
    maxAlloc=1,
    lambda_l1=0,
    lambda_l2=0,
    assetsOrder=None,
):
    """
    Mean-Variance portfolio for a target return

    Parameters
    ----------
    meanVec : Array
        A vector of mean returns of assets
    SigMat : Matrix
        A covariance matrix of appropriate dimensions
    retTarget : Float
        Target return percentage. Values specified between 0 and 100
    LongShort : Float
        Takes value between 0 and 1
    maxAlloc : Float
        Takes value between 0 and 1. Specifies the maximum weight an asset can get
    lambda_l1 : Float
        Takes a value greater than 0. Specifies L1 penalty
    lambda_l2 : Float
        Takes a value greater than 0. Specifies L2 penalty

    Returns
    -------
    w_opt : Array
        Returns the weights of given to each asset in form of a numpy array
    var_opt : Float
        Returns the variance of the portfolio
    """
    dailyRetTarget = 100 * ((retTarget / 100 + 1) ** (1 / 250) - 1)
    minEret = min(meanVec)
    maxEret = max(meanVec)
    if (dailyRetTarget < minEret) or (maxEret < dailyRetTarget):
        part1 = minEret
        part2 = min(maxEret, dailyRetTarget)
        dailyRetTarget = max(part1, part2)

    d = sigMat.shape[0]
    if assetsOrder:
        temp = sigMat[:, assetsOrder]
        sigMat = temp[assetsOrder, :]
        meanVec = meanVec[assetsOrder]
    if lambda_l2:
        sigMat = sigMatShrinkage(sigMat, lambda_l2)
        sigMat, e_min = SymPDcovmatrix(sigMat)
    else:
        sigMat, e_min = SymPDcovmatrix(sigMat)

    if longShort == 0:
        Aeq = np.ones(d)
        Beq = 1
        LB = np.zeros(d)
        UB = maxAlloc * np.ones(d)

        if assetsOrder:
            L_ine = np.hstack([-np.inf, -np.ones(d - 1)])
            tau = dailyRetTarget
            A = -meanVec
            B = -tau
            A = np.vstack([A, -1 * Dmat(d, 1)])
            B = np.hstack([B, np.zeros(d - 1)])
        else:
            tau = dailyRetTarget
            A = -meanVec
            B = -tau
            L_ine = -np.inf

        if lambda_l1:
            meanVec = -lambda_l1 * meanVec
        else:
            meanVec = -np.zeros(d)

        A = np.vstack([A, Aeq, np.eye(d)])
        l = np.hstack([L_ine, Beq, LB])
        u = np.hstack([B, Beq, UB])
        P = sparse.csc_matrix(sigMat)
        A = sparse.csc_matrix(A)

        prob = osqp.OSQP()
        # Setup workspace
        prob.setup(P, -meanVec, A, l, u, verbose=False)
        # Solve problem
        res = prob.solve()
        w_opt = res.x
        if not w_opt.all():
            w_opt = np.ones(d) / d

    elif longShort != 0:
        A = np.hstack([np.zeros(d), np.ones(d), np.zeros(d)])
        B = 1 + abs(longShort)
        Grenze = min(abs(longShort), maxAlloc)

        if assetsOrder:
            tau = dailyRetTarget
            A = np.vstack([A, np.hstack([-meanVec, np.zeros(2 * d)])])
            B = np.hstack([B, -tau])
            A = np.vstack([A, np.hstack([-1 * Dmat(d, 1), np.zeros((d - 1, 2 * d))])])
            B = np.hstack([B, np.zeros(d - 1)])
            L_ine = np.hstack([0, -np.inf, -(1 + 2 * Grenze) * np.ones(d - 1)])
        else:
            tau = dailyRetTarget
            A = np.vstack([A, np.hstack([-meanVec, np.zeros(2 * d)])])
            B = np.hstack([B, -tau])
            L_ine = np.hstack([0, -np.inf])

        Aeq = np.vstack(
            [
                np.hstack([np.eye(d), -np.eye(d), np.eye(d)]),
                np.hstack([np.ones((1, d)), np.zeros((1, d)), np.zeros((1, d))]),
            ]
        )
        Beq = np.hstack([np.zeros(d), 1])
        LB = np.hstack([-Grenze * np.ones(d), np.zeros(2 * d)])
        UB = maxAlloc * np.ones(3 * d)
        sigMat3d = np.vstack(
            [np.hstack([sigMat, np.zeros((d, 2 * d))]), np.zeros((2 * d, 3 * d))]
        )
        sigMat3d = sigMat3d + np.diag(
            np.hstack([-0.1 * e_min * np.ones(d), 0.1 * e_min * np.ones(2 * d)])
        )

        if lambda_l1:
            meanvec3d = np.hstack([np.zeros(d), -lambda_l1 * np.ones(2 * d)])
        else:
            meanvec3d = np.hstack([np.zeros(d), np.zeros(2 * d)])

        A = np.vstack([A, Aeq, np.eye(3 * d)])
        l = np.hstack([L_ine, Beq, LB])
        u = np.hstack([B, Beq, UB])
        A = sparse.csc_matrix(A)
        sigMat3d = sparse.csc_matrix(sigMat3d)
        prob = osqp.OSQP()
        # Setup workspace
        prob.setup(sigMat3d, -meanvec3d, A, l, u, verbose=False)
        # Solve problem
        res = prob.solve()
        wuv_opt = res.x
        if not wuv_opt.all():
            w_opt = np.ones(d) / d
        else:
            w_opt = wuv_opt[:d]
    t = np.dot(w_opt, sigMat)
    Var_opt = np.dot(t, w_opt.transpose())
    if assetsOrder:
        w_opt = w_opt[assetsOrder]
    # if exitflag!=1:
    # print("minimumVariancePortfolio: Exitflag different than 1 in quadprog")
    return w_opt, Var_opt


def check_missing(df_logret):
    """
    function to check the missing values and delete the stocks with missing value

    Parameters
    ----------
    df_logret : pandas.core.frame.DataFrame
       the price window

    Returns
    -------
    res : pandas.core.frame.DataFrame
       the price window without missing value
    """
    df_logret = df_logret.transpose()
    flag = np.zeros(len(df_logret))
    for i in range(len(df_logret)):
        if df_logret.iloc[i, :].isnull().any():
            flag[i] = 0
        else:
            flag[i] = 1
    df_logret["missing_flag"] = flag
    res = df_logret.loc[df_logret["missing_flag"] == 1]
    return res.transpose()


def rollingwindow_backtest(
    optimizerName,
    data,
    window_size,
    rebalance_time,
    maxAlloc=1,
    riskAversion=0,
    meanQuantile=0,
    retTarget=0,
    longShort=0,
    lambda_l1=0,
    lambda_l2=0,
    assetsOrder=None,
):
    """
    function do the rolling window back test

    Parameters
    ----------
    optimizerName : String
        The name of the optimizer to use for rolling window exercise
    data : Dictionary
        Data with Ticker, Date and Adjusted Close price
    whindow_size : int
        parameter for the size of rolling window
    rebalance_time : int
        rebalance time of rolling window test
    maxAlloc : Float
        maximum allocation. Takes values between 0 and 1
    riskAversion : Float
        Riske Aversion for your portfolio. Takes values greater than 0
    meanQuantile : Float
        Takes values between 0 and 1
    RetTarget : Float
        Target returns in percentage for optimizer. Takes values between 0 and 100
    LongShort : Float
        Takes value between 0 and 1
    maxAlloc : Float
        Takes value between 0 and 1. Specifies the maximum weight an asset can get
    lambda_l1 : Float
        Takes a value greater than 0. Specifies L1 penalty
    lambda_l2 : Float
        Takes a value greater than 0. Specifies L2 penalty

    Returns
    -------
    R : 2d array
        return matrix depends on the rebalance time
    logret: 2d array
        log return matrix for each stocks
    w_all: 2d array
        optimal weight for each revalance time
    rownames: array
        date time of rolling window test

    Notes
    -------
    Note for now we have provided additional parameters that'll be used in future versions of the optimizers
    """
    df = pd.DataFrame(data)

    df.columns = ["date", "ticker", "price"]
    df1 = df.pivot_table(index=["date"], columns="ticker", values=["price"])
    df1.columns = [col[1] for col in df1.columns.values]
    df_logret = 100 * (np.log(df1) - np.log(df1.shift(1)))
    df_logret = df_logret[1:]
    logret = np.array(df_logret)
    n = logret.shape[0]
    d = rebalance_time
    start = window_size
    R = None
    portfolio_return = None
    w_all = None
    for i in range(start, n, d):
        k = 0
        w_opt = np.zeros(df1.shape[1])
        # import pdb; pdb.set_trace()
        window = check_missing(df_logret[i - window_size : i] / 100)
        m = window.shape[0]
        sample_stocks = window.columns
        logret_window = np.array(window.iloc[: n - 1])
        sigMat = np.cov(logret_window, rowvar=False)
        meanVec = np.mean(logret_window, axis=0) / 100

        if optimizerName == "minimumVariancePortfolio":
            w_sample, _ = minimumVariancePortfolio(
                sigMat,
                float(maxAlloc),
                float(longShort),
                float(lambda_l1),
                float(lambda_l2),
            )

        elif optimizerName == "meanVariancePortfolioReturnsTarget":
            w_sample, _ = meanVariancePortfolioReturnsTarget(
                meanVec,
                sigMat,
                float(retTarget),
                float(maxAlloc),
                float(longShort),
                float(lambda_l1),
                float(lambda_l2),
            )
        elif optimizerName == "test":
            import test
            test.displayText()
            
        for j in range(df1.shape[1]):
            if df1.columns[j] in sample_stocks:
                w_opt[j] = w_sample[k]
                k += 1

        if w_all is None:
            w_all = w_opt
        else:
            w_all = np.vstack([w_all, w_opt])

        if (i + d) < n:
            if R is None:
                logret_sample = np.nan_to_num(logret[i : i + d], nan=0)
                simple_returns = 100 * (math.exp(1) ** (logret_sample / 100) - 1)
                R = np.dot(w_opt, simple_returns.transpose())
            else:
                logret_sample = np.nan_to_num(logret[i : i + d], nan=0)
                simple_returns = 100 * (math.exp(1) ** (logret_sample / 100) - 1)
                R = np.hstack([R, np.dot(w_opt, simple_returns.transpose())])
        elif (i + d) >= n:
            logret_sample = np.nan_to_num(logret[i:], nan=0)
            simple_returns = 100 * (math.exp(1) ** (logret_sample / 100) - 1)
            R = np.hstack([R, np.dot(w_opt, simple_returns.transpose())])
    rownames = df1.index[start + 1 :]
    return R, df_logret, w_all, rownames


if __name__ == "__main__":
    pass
