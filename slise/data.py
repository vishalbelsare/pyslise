# This script contains functions for modifying data

from typing import Union, Tuple, NamedTuple
import numpy as np
from scipy.special import logit, expit as sigmoid


def add_intercept_column(X: np.ndarray) -> np.ndarray:
    """
        Add a constant column of ones to the matrix
    """
    if len(X.shape) == 1:
        return np.concatenate(([1.0], X))
    return np.concatenate((np.ones((X.shape[0], 1)), X), 1)


def remove_intercept_column(X: np.ndarray) -> np.ndarray:
    """
        Remove the first column
    """
    if len(X.shape) == 1:
        return X[1:]
    return X[:, 1:]


def remove_constant_columns(
    X: np.ndarray, epsilon: Union[float, None] = None
) -> Tuple[np.ndarray, np.ndarray]:
    """Remove columns that are constant from a matrix

    Args:
        X (np.ndarray): the matrix
        epsilon (Union[float, None], optional): treshold for constant (std < epsilon). Defaults to machine epsilon.

    Returns:
        Tuple[np.ndarray, np.ndarray]: A tuple of the reduced matrix and a mask showing which columns where retained
    """
    if epsilon is None:
        epsilon = np.finfo(X.dtype).eps
    std = np.std(X, 0)
    mask = std > epsilon
    return X[:, mask], mask


def add_constant_columns(
    X: np.ndarray, mask: Union[np.ndarray, None], intercept: bool = False
) -> np.ndarray:
    """Add (back) contant columns to a matrix

    Args:
        X (np.ndarray): the matrix
        mask (Union[np.ndarray, None]): a boolean array showing which columns are already in the matrix
        intercept (bool, optional): does X has an intercept (added to it after constant columns where removed). Defaults to False.

    Returns:
        np.ndarray: a matrix with new columns filled with zeros
    """
    if mask is None:
        return X
    if intercept:
        mask = np.concatenate(([True], mask))
    if len(X.shape) < 2:
        X2 = np.zeros(len(mask), X.dtype)
        X2[mask] = X
        return X2
    else:
        X2 = np.zeros((X.shape[0], len(mask)), X.dtype)
        X2[:, mask] = X
        return X2


def unscale_model(
    model: np.ndarray,
    x_center: np.ndarray,
    x_scale: np.ndarray,
    y_center: float = 0.0,
    y_scale: float = 1.0,
    columns: Union[np.ndarray, None] = None,
) -> np.ndarray:
    """Scale a linear model such that it matches unnormalised data

    Args:
        model (np.ndarray): the model for normalised data
        x_center (np.ndarray): the center used for normalising X
        x_scale (np.ndarray): the scale used for normalising X
        y_center (float, optional): the scale used for normalising y. Defaults to 0.0.
        y_scale (float, optional): the center used for normalising y. Defaults to 1.0.

    Returns:
        np.ndarray: the unscaled model
    """
    if len(model) == len(x_center):
        model = np.concatenate((np.zeros(1, x_center.dtype), model))
    else:
        model = model.copy()
    model[0] = (model[0] - np.sum(model[1:] * x_center / x_scale)) * y_scale + y_center
    model[1:] = model[1:] / x_scale * y_scale
    if columns is not None:
        return add_constant_columns(model, columns, True)
    else:
        return model


def normalise_robust(
    x: np.ndarray, epsilon: Union[float, None] = None
) -> Tuple[np.ndarray, Union[float, np.ndarray], Union[float, np.ndarray]]:
    """A robust version of normalisation that uses median and mad (median absolute deviation).
        Any zeros in the scale are replaced by ones to avoid division by zero.

    Args:
        x (np.ndarray): the vector or tensor to normalise
        epsilon (Union[float, None], optional): threshold for the scale being zero. Defaults to machine epsilon.

    Returns:
        Tuple[np.ndarray, Union[float, np.ndarray], Union[float, np.ndarray]]: tuple of normalised x, center and scale
    """
    if epsilon is None:
        epsilon = np.finfo(x.dtype).eps
    if len(x.shape) < 2:
        center = np.median(x)
        x = x - center
        scale = np.median(np.abs(x))
        if scale <= epsilon:
            scale = 1.0
        return x / scale, center, scale
    else:
        center = np.median(x, 0)
        x = x - center[None, :]
        scale = np.median(np.abs(x), 0)
        scale[scale <= epsilon] = 1.0
        return x / scale[None, :], center, scale


def scale_same(
    x: Union[np.ndarray, float],
    center: Union[float, np.ndarray],
    scale: Union[float, np.ndarray],
    constant_colums: Union[np.ndarray, None] = None,
    remove_columns: bool = True,
) -> np.ndarray:
    """Scale a matrix or vector the same way as another

    Args:
        x (np.ndarray): the matrix/vector to scale
        center (Union[float, np.ndarray]): the center used for the previous scaling
        scale (Union[float, np.ndarray]): the scale used for the previous scaling
        constant_colums (Union[np.ndarray, None], optional): boolean mask of constant columns. Defaults to None.
        remove_columns (bool, optional): remove constant columns. Defaults to True.

    Returns:
        np.ndarray: the scaled matrix/vector
    """
    if isinstance(x, float) or len(x.shape) < 2:
        if constant_colums is not None:
            if not remove_columns:
                y = np.zeros_like(x)
                y[constant_colums] = (x[constant_colums] - center) / scale
                return y
            x = x[constant_colums]
        return (x - center) / scale
    else:
        if constant_colums is not None:
            if not remove_columns:
                y = np.zeros_like(x)
                y[:, constant_colums] = (
                    x[:, constant_colums] - center[None, :]
                ) / scale[None, :]
                return y
            x = x[:, constant_colums]
        return (x - center[None, :]) / scale[None, :]


class DataScaling(NamedTuple):
    # Container class for scaling information
    x_center: np.ndarray
    x_scale: np.ndarray
    y_center: float
    y_scale: float
    columns: np.ndarray

    def scale_x(self, x: np.ndarray, remove_columns: bool = True) -> np.ndarray:
        # Scale a new x vector
        return scale_same(x, self.x_center, self.x_scale, self.columns, remove_columns)

    def scale_y(self, y: Union[float, np.ndarray]) -> Union[float, np.ndarray]:
        # Scale a new y vector
        return scale_same(y, self.y_center, self.y_scale)

    def unscale_model(self, model: np.ndarray) -> np.ndarray:
        # Unscale a linear model
        return unscale_model(
            model,
            self.x_center,
            self.x_scale,
            self.y_center,
            self.y_scale,
            self.columns,
        )


def pca_simple(
    x: np.ndarray, dimensions: int = 10, tolerance: float = 1e-10
) -> Tuple[np.ndarray, np.ndarray]:
    """Fit and use PCA for dimensionality reduction

    Args:
        X (np.ndarray): the matrix to reduce
        dimensions (int, optional): the number of dimensions to return. Defaults to 10.
        tolerance (float, optional): threshold for variance being zero. Defaults to 1e-10.

    Returns:
        Tuple[np.ndarray, np.ndarray]: tuple of the reduced matrix and PCA rotation matrix
    """
    if len(x.shape) == 1:
        return x, 1.0
    dimensions = min(dimensions, *x.shape)
    u, s, v = np.linalg.svd(x, False, True, False)
    dimensions = max(1, np.sum(s[: min(dimensions, len(s))] > s[0] * tolerance))
    return u[:, :dimensions].dot(np.diag(s[:dimensions])), v[:dimensions, :]


def pca_rotate(x: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Use a trained PCA for dimensionality reduction

    Args:
        X (np.ndarray): the matrix to reduce
        v (np.ndarray): the PCA rotation matrix

    Returns:
        np.ndarray: the reduced matrix
    """
    return x @ v.T


def pca_invert(x: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Revert a PCA dimensionality reduction

    Args:
        X (np.ndarray): the matrix to expand
        v (np.ndarray): the PCA rotation matrix

    Returns:
        np.ndarray: the expanded matrix
    """
    return x @ v


def pca_rotate_model(model: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Transform a linear model to work in PCA reduced space

    Args:
        model (np.ndarray): the linear model
        v (np.ndarray): the PCA rotation matrix

    Returns:
        np.ndarray: the transformed linear model
    """
    if len(model) > v.shape[1]:
        return np.concatenate((model[:1], v @ model[1:]))
    return v @ model


def pca_invert_model(model: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Transform a linear model from PCA space to "normal" space

    Args:
        model (np.ndarray): the linear model (in PCA space)
        v (np.ndarray): the PCA rotation matrix

    Returns:
        np.ndarray: the transformed model
    """
    if len(model) > v.shape[0]:
        return np.concatenate((model[:1], v.T @ model[1:]))
    return v.T @ model
