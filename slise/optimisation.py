# This script contains the optimisations for SLISE (Graduated Optimisation and OWL-QN)

from math import log
from warnings import warn
import numpy as np
from numba import jit
from lbfgs import fmin_lbfgs, LBFGSError
from scipy.optimize import brentq
from slise.utils import (
    sigmoid,
    log_sigmoid,
    dlog_sigmoid,
    log_sum_special,
    SliseWarning,
)


def loss_smooth(
    alpha: np.ndarray,
    X: np.ndarray,
    Y: np.ndarray,
    epsilon: float = 0.1,
    lambda1: float = 0,
    lambda2: float = 0,
    beta: float = 100,
) -> float:
    """
        Smoothed (with sigmoid) version of the loss
    """
    epsilon *= epsilon
    distances = ((X @ alpha) - Y) ** 2
    subset = sigmoid(beta * (epsilon - distances))
    residuals = np.minimum(0, distances - epsilon * len(Y))
    loss = np.sum(subset * residuals) / len(Y)
    if lambda1 > 0:
        loss += lambda1 * np.sum(np.abs(alpha))
    if lambda2 > 0:
        loss += lambda2 * np.sum(alpha * alpha)
    return loss


@jit(nopython=True, fastmath=True, parallel=True, cache=True)
def loss_residuals(
    alpha: np.ndarray,
    residuals2: np.ndarray,
    epsilon2: float = 0.01,
    lambda1: float = 0,
    lambda2: float = 0,
    beta: float = 100,
) -> float:
    """
        Smoothed (with sigmoid) version of the loss, that takes already calculated residuals
    """
    # Takes squared residuals and epsilons
    subset = 1 / (1 + np.exp(-beta * (epsilon2 - residuals2)))
    # subset = sigmoid(beta * (epsilon2 - residuals2))
    residuals = np.minimum(0, residuals2 - epsilon2 * len(residuals2))
    loss = np.sum(subset * residuals) / len(residuals2)
    if lambda1 > 0:
        loss += lambda1 * np.sum(np.abs(alpha))
    if lambda2 > 0:
        loss += lambda2 * np.sum(alpha * alpha)
    return loss


def loss_sharp(
    alpha: np.ndarray,
    X: np.ndarray,
    Y: np.ndarray,
    epsilon: float = 0.1,
    lambda1: float = 0,
    lambda2: float = 0,
) -> float:
    """
        Exact (combinatorial) version of the loss
    """
    epsilon *= epsilon
    distances = ((X @ alpha) - Y) ** 2
    loss = np.sum(distances[distances < epsilon] - (epsilon * len(Y))) / len(Y)
    if lambda1 > 0:
        loss += lambda1 * np.sum(np.abs(alpha))
    if lambda2 > 0:
        loss += lambda2 * np.sum(alpha * alpha)
    return loss


@jit(nopython=True, fastmath=True, parallel=True, cache=True)
def loss_numba(
    alpha: np.ndarray,
    X: np.ndarray,
    Y: np.ndarray,
    epsilon: float,
    lambda2: float,
    beta: float,
) -> (float, np.ndarray):
    """
        Smoothed (with sigmoid) version of the loss, that also calculates
        the gradient (sped up with numba)
    """
    epsilon *= epsilon
    distances = (X @ alpha) - Y
    distances2 = distances ** 2
    n = len(Y)
    # Loss
    subset = 1 / (1 + np.exp(-beta * (epsilon - distances2)))
    residuals = np.minimum(0, distances2 - (epsilon * n))
    loss = np.sum(subset * residuals) / n
    # Gradient
    k1 = 2.0 / n
    k2 = (-2.0 * beta / n) * (subset - subset ** 2)
    distances[residuals == 0] = 0.0
    grad = ((subset * k1) + (residuals * k2)) * distances
    grad = np.expand_dims(grad, 0) @ X
    # Lambda
    if lambda2 > 0:
        loss = loss + lambda2 * np.sum(alpha * alpha)
        grad = grad + (lambda2 * 2) * alpha
    return loss, grad


def owlqn(
    alpha: np.ndarray,
    X: np.ndarray,
    Y: np.ndarray,
    epsilon: float = 0.1,
    lambda1: float = 0,
    lambda2: float = 0,
    beta: float = 100,
    max_iterations: int = 200,
) -> np.ndarray:
    """
        Optimise a smoothed loss with owlqn
    """
    assert lambda1 >= 0, "lambda1 must be >= 0"

    def f(alpha: np.ndarray, gradient: np.ndarray) -> float:
        loss, grad = loss_numba(alpha, X, Y, epsilon, lambda2, beta)
        gradient[:] = grad
        return loss

    try:  # PyLBFGS throws an error if max_iterations is exceeded, this is a workaround to convert it into a warning

        def p(x, g, fx, xnorm, gnorm, step, k, num_eval, *args):
            if k >= max_iterations:
                alpha[:] = x

        alpha = fmin_lbfgs(
            f=f,
            x0=alpha,
            progress=p,
            orthantwise_c=lambda1,
            max_iterations=max_iterations,
            line_search="wolfe" if lambda1 > 0 else "default",
        )
    except LBFGSError as error:
        if (
            error.args[0]
            != "The algorithm routine reaches the maximum number of iterations."
        ):
            raise error
        else:
            warn(
                "An optimisation step reaches the maximum number of iterations.",
                SliseWarning,
            )
    return alpha


def log_approximation_ratio(
    residuals2: np.ndarray, epsilon2: float, beta1: float, beta2: float
) -> float:
    """
        Calculate log(K), where K is the approximation ratio between two smoothed losses
    """
    if beta1 >= beta2:
        return 0
    log_f = lambda r, beta: log_sigmoid(beta * (epsilon2 - r))
    dlog_g = lambda r: -beta1 * dlog_sigmoid(
        beta1 * (epsilon2 - r)
    ) + beta2 * dlog_sigmoid(beta2 * (epsilon2 - r))
    if dlog_g(0) < 0:
        a = brentq(dlog_g, 0, epsilon2)
        log_k = min(
            log_f(0, beta1) - log_f(0, beta2), log_f(a, beta1) - log_f(a, beta2)
        )
    else:
        log_k = log_f(0, beta1) - log_f(0, beta2)
    phi = np.maximum(0, epsilon2 - residuals2 / len(residuals2))
    log_K = (
        log_sum_special(log_f(residuals2, beta1), phi)
        - log_k
        - log_sum_special(log_f(residuals2, beta2), phi)
    )
    return log_K


def next_beta(
    residuals2: np.ndarray,
    epsilon2: float = 0.01,
    beta: float = 0,
    beta_max: float = 2500,
    log_max_approx: float = 0.14,
    min_beta_step: float = 0.0005,
    **kwargs,
) -> float:
    """
        Calculate the next beta for the graduated optimisation
    """
    if beta >= beta_max:
        return beta
    log_approx = log_approximation_ratio(residuals2, epsilon2, beta, beta_max)
    if log_approx <= log_max_approx:
        return beta_max
    else:
        f = (
            lambda b: log_approximation_ratio(residuals2, epsilon2, beta, b)
            - log_max_approx
        )
        beta_min = beta + min_beta_step * (beta_max + beta)
        return max(brentq(f, beta, beta_max), beta_min)


def matching_epsilon(residuals2: np.ndarray, epsilon2: float, beta: float) -> float:
    """
        Approximately calculate the epsilon that minimises the approximation ratio to the exact loss
    """
    residuals2 = np.sort(residuals2)
    loss = sigmoid(beta * (epsilon2 - residuals2))
    i = np.argmax(np.arange(len(residuals2)) * loss)
    return residuals2[i] ** 0.5


def debug_log(
    alpha: np.ndarray,
    X: np.ndarray,
    Y: np.ndarray,
    epsilon: float = 0.1,
    lambda1: float = 0,
    lambda2: float = 0,
    beta: float = 0,
):
    """
        Print the log statement for a graduated optimisation step
    """
    residuals = (X @ alpha - Y) ** 2
    loss = loss_sharp(alpha, X, Y, epsilon, lambda1, lambda2)
    bloss = loss_residuals(alpha, residuals, epsilon ** 2, lambda1, lambda2, beta)
    epss = matching_epsilon(residuals, epsilon ** 2, beta)
    beta = beta * epsilon ** 2
    print(
        f"beta: {beta:5.3f}    epsilon*: {epss:.3f}    Loss: {loss:6.2f}    B-Loss: {bloss:6.2f}"
    )


def graduated_optimisation(
    alpha: np.ndarray,
    X: np.ndarray,
    Y: np.ndarray,
    epsilon: float = 0.1,
    lambda1: float = 0,
    lambda2: float = 0,
    beta: float = 0,
    beta_max: float = 25,
    max_approx: float = 1.15,
    max_iterations: int = 200,
    debug: bool = False,
    **kwargs,
) -> np.ndarray:
    """Optimise alpha using graduated optimisation

    Arguments:
        alpha {np.ndarray} -- the initial alpha
        X {np.ndarray} -- the data matrix
        Y {np.ndarray} -- the response vector

    Keyword Arguments:
        epsilon {float} -- the error tolerance (default: {0.1})
        lambda1 {float} -- L1 regularisation (default: {0})
        lambda2 {float} -- L2 regularisation (default: {0})
        beta {float} -- the initial beta (default: {0})
        beta_max {float} -- the stopping beta (default: {25})
        max_approx {float} -- target approximation ratio when increasing beta (default: {1.15})
        max_iterations {int} -- maximum number of iterations for owl-qn (default: {200})
        debug {bool} -- print debug logs after each optimisation step (default: {False})

    Returns:
        np.ndarray -- the optimised alpha
    """
    X = np.asfortranarray(X, dtype=np.float64)
    Y = np.asfortranarray(Y, dtype=np.float64)
    beta_max = beta_max / epsilon ** 2
    max_approx = log(max_approx)
    while beta < beta_max:
        alpha = owlqn(alpha, X, Y, epsilon, lambda1, lambda2, beta, max_iterations)
        if debug:
            debug_log(alpha, X, Y, epsilon, lambda1, lambda2, beta)
        beta = next_beta(
            (X @ alpha - Y) ** 2, epsilon ** 2, beta, beta_max, max_approx, **kwargs
        )
    alpha = owlqn(alpha, X, Y, epsilon, lambda1, lambda2, beta, max_iterations * 4)
    if debug:
        debug_log(alpha, X, Y, epsilon, lambda1, lambda2, beta)
    return alpha
