"""
Testing DKI
"""

from __future__ import division, print_function, absolute_import

import numpy as np

from nose.tools import (assert_true, assert_equal,
                        assert_almost_equal, assert_raises)
from numpy.testing import (assert_array_equal, assert_array_almost_equal,
                           assert_)

from dipy.sims.voxel import multi_tensor_dki

import dipy.reconst.dti as dti

import dipy.reconst.dki as dki

from dipy.io.gradients import read_bvals_bvecs

from dipy.core.gradients import gradient_table

from dipy.data import get_data

from dipy.reconst.dti import (from_lower_triangular, decompose_tensor)


fimg, fbvals, fbvecs = get_data('small_64D')
bvals, bvecs = read_bvals_bvecs(fbvals, fbvecs)
gtab = gradient_table(bvals, bvecs)

# 2 shells for techniques that requires multishell data
bvals_2s = np.concatenate((bvals, bvals * 2), axis=0)
bvecs_2s = np.concatenate((bvecs, bvecs), axis=0)
gtab_2s = gradient_table(bvals_2s, bvecs_2s)


def test_dki_fits():
    """DKI fits are tested"""

    # Signals of two crossing fibers are simulated
    mevals = np.array([[0.00099, 0, 0], [0.00226, 0.00087, 0.00087],
                       [0.00099, 0, 0], [0.00226, 0.00087, 0.00087]])
    angles = [(80, 10), (80, 10), (20, 30), (20, 30)]
    fie = 0.49
    frac = [fie*50, (1 - fie)*50, fie*50, (1 - fie)*50]
    signal, dt, kt = multi_tensor_dki(gtab_2s, mevals, angles=angles,
                                      fractions=frac, snr=None)

    evals, evecs = decompose_tensor(from_lower_triangular(dt))
    ref_params = np.concatenate((evals, evecs[0], evecs[1], evecs[2], kt),
                                axis=0)

    # OLS fitting
    dkiM = dki.DKIModel(gtab_2s)
    dkiF = dkiM.fit(signal)

    assert_array_almost_equal(dkiF.model_params, ref_params)
    
    # WLS fitting
    dki_wlsM = dki.DKIModel(gtab_2s, fit_method="WLS_DKI")
    dki_wlsF = dki_wlsM.fit(signal)

    assert_array_almost_equal(dki_wlsF.model_params, ref_params)


def wls_fit_dki(design_matrix, data, min_signal=1):
    r"""
    WLS fit implemented by Maurizio
    """

    tol = 1e-6
    if min_signal <= 0:
        raise ValueError('min_signal must be > 0')

    data = np.asarray(data)
    data_flat = data.reshape((-1, data.shape[-1]))
    dki_params = np.empty((len(data_flat), 6, 3))
    min_diffusivity = tol / -design_matrix.min()

    ols_fit = _ols_fit_matrix(design_matrix)
   
    for param, sig in zip(dki_params, data_flat):
        param[0], param[1:4], param[4], param[5] = _wls_iter(ols_fit, design_matrix, sig, min_signal, min_diffusivity)
        
    dki_params.shape=data.shape[:-1]+(18,)
    dki_params=dki_params
    return dki_params


def _ols_fit_matrix(design_matrix):
    """
    (implemented by Maurizio)
    Helper function to calculate the ordinary least squares (OLS)
    fit as a matrix multiplication. Mainly used to calculate WLS weights. Can
    be used to calculate regression coefficients in OLS but not recommended.

    See Also:
    ---------
    wls_fit_tensor, ols_fit_tensor

    Example:
    --------
    ols_fit = _ols_fit_matrix(design_mat)
    ols_data = np.dot(ols_fit, data)
    """

    U, S, V = np.linalg.svd(design_matrix, False)
    return np.dot(U, U.T)
    

def _wls_iter(ols_fit, design_matrix, sig, min_signal, min_diffusivity):
    ''' Helper function used by wls_fit_tensor.
    '''
    sig = np.maximum(sig, min_signal)  # throw out zero signals
    log_s = np.log(sig)
    w = np.exp(np.dot(ols_fit, log_s))
    result = np.dot(np.linalg.pinv(design_matrix * w[:, None]), w * log_s)
    D=result[:6]
    tensor=from_lower_triangular(D)
    MeanD_square=((tensor[0,0]+tensor[1,1]+tensor[2,2])/3.)**2  
    K_tensor_elements=result[6:21]/MeanD_square
    return decompose_tensors(tensor, K_tensor_elements, min_diffusivity=min_diffusivity)

