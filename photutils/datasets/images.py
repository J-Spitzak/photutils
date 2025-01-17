# Licensed under a 3-clause BSD style license - see LICENSE.rst
"""
This module provides tools for making simulated images for documentation
examples and tests.
"""

import math
import warnings

import numpy as np
from astropy.convolution import discretize_model
from astropy.modeling import models
from astropy.nddata import overlap_slices
from astropy.table import QTable
from astropy.utils.exceptions import AstropyUserWarning

from photutils.psf import IntegratedGaussianPRF
from photutils.utils._coords import make_random_xycoords
from photutils.utils._parameters import as_pair
from photutils.utils._progress_bars import add_progress_bar

__all__ = ['make_model_sources_image', 'make_gaussian_sources_image',
           'make_4gaussians_image', 'make_100gaussians_image',
           'make_gaussian_prf_sources_image',
           'make_test_psf_data']


def make_model_sources_image(shape, model, source_table, oversample=1):
    """
    Make an image containing sources generated from a user-specified
    model.

    Parameters
    ----------
    shape : 2-tuple of int
        The shape of the output 2D image.

    model : 2D astropy.modeling.models object
        The model to be used for rendering the sources.

    source_table : `~astropy.table.Table`
        Table of parameters for the sources.  Each row of the table
        corresponds to a source whose model parameters are defined by
        the column names, which must match the model parameter names.
        Column names that do not match model parameters will be ignored.
        Model parameters not defined in the table will be set to the
        ``model`` default value.

    oversample : float, optional
        The sampling factor used to discretize the models on a pixel
        grid.  If the value is 1.0 (the default), then the models will
        be discretized by taking the value at the center of the pixel
        bin.  Note that this method will not preserve the total flux of
        very small sources.  Otherwise, the models will be discretized
        by taking the average over an oversampled grid.  The pixels will
        be oversampled by the ``oversample`` factor.

    Returns
    -------
    image : 2D `~numpy.ndarray`
        Image containing model sources.

    See Also
    --------
    make_random_models_table, make_gaussian_sources_image

    Examples
    --------
    .. plot::
        :include-source:

        import matplotlib.pyplot as plt
        from astropy.modeling.models import Moffat2D
        from photutils.datasets import (make_model_sources_image,
                                        make_random_models_table)

        model = Moffat2D()
        n_sources = 10
        shape = (100, 100)
        param_ranges = {'amplitude': [100, 200],
                        'x_0': [0, shape[1]],
                        'y_0': [0, shape[0]],
                        'gamma': [5, 10],
                        'alpha': [1, 2]}
        sources = make_random_models_table(n_sources, param_ranges,
                                           seed=0)

        data = make_model_sources_image(shape, model, sources)
        plt.imshow(data)
    """
    image = np.zeros(shape, dtype=float)
    yidx, xidx = np.indices(shape)

    params_to_set = []
    for param in source_table.colnames:
        if param in model.param_names:
            params_to_set.append(param)

    # Save the initial parameter values so we can set them back when
    # done with the loop. It's best not to copy a model, because some
    # models (e.g., PSF models) may have substantial amounts of data in
    # them.
    init_params = {param: getattr(model, param) for param in params_to_set}

    try:
        for source in source_table:
            for param in params_to_set:
                setattr(model, param, source[param])

            if oversample == 1:
                image += model(xidx, yidx)
            else:
                image += discretize_model(model, (0, shape[1]),
                                          (0, shape[0]), mode='oversample',
                                          factor=oversample)
    finally:
        for param, value in init_params.items():
            setattr(model, param, value)

    return image


def make_gaussian_sources_image(shape, source_table, oversample=1):
    r"""
    Make an image containing 2D Gaussian sources.

    Parameters
    ----------
    shape : 2-tuple of int
        The shape of the output 2D image.

    source_table : `~astropy.table.Table`
        Table of parameters for the Gaussian sources.  Each row of the
        table corresponds to a Gaussian source whose parameters are
        defined by the column names.  With the exception of ``'flux'``,
        column names that do not match model parameters will be ignored
        (flux will be converted to amplitude).  If both ``'flux'`` and
        ``'amplitude'`` are present, then ``'flux'`` will be ignored.
        Model parameters not defined in the table will be set to the
        default value.

    oversample : float, optional
        The sampling factor used to discretize the models on a pixel
        grid.  If the value is 1.0 (the default), then the models will
        be discretized by taking the value at the center of the pixel
        bin.  Note that this method will not preserve the total flux of
        very small sources.  Otherwise, the models will be discretized
        by taking the average over an oversampled grid.  The pixels will
        be oversampled by the ``oversample`` factor.

    Returns
    -------
    image : 2D `~numpy.ndarray`
        Image containing 2D Gaussian sources.

    See Also
    --------
    make_model_sources_image, make_random_gaussians_table

    Examples
    --------
    .. plot::
        :include-source:

        import matplotlib.pyplot as plt
        import numpy as np
        from astropy.table import QTable
        from photutils.datasets import (make_gaussian_sources_image,
                                        make_noise_image)

        # make a table of Gaussian sources
        table = QTable()
        table['amplitude'] = [50, 70, 150, 210]
        table['x_mean'] = [160, 25, 150, 90]
        table['y_mean'] = [70, 40, 25, 60]
        table['x_stddev'] = [15.2, 5.1, 3., 8.1]
        table['y_stddev'] = [2.6, 2.5, 3., 4.7]
        table['theta'] = np.radians(np.array([145., 20., 0., 60.]))

        # make an image of the sources without noise, with Gaussian
        # noise, and with Poisson noise
        shape = (100, 200)
        image1 = make_gaussian_sources_image(shape, table)
        image2 = image1 + make_noise_image(shape, distribution='gaussian',
                                           mean=5., stddev=5.)
        image3 = image1 + make_noise_image(shape, distribution='poisson',
                                           mean=5.)

        # plot the images
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(8, 12))
        ax1.imshow(image1, origin='lower', interpolation='nearest')
        ax1.set_title('Original image')
        ax2.imshow(image2, origin='lower', interpolation='nearest')
        ax2.set_title('Original image with added Gaussian noise'
                      r' ($\mu = 5, \sigma = 5$)')
        ax3.imshow(image3, origin='lower', interpolation='nearest')
        ax3.set_title(r'Original image with added Poisson noise ($\mu = 5$)')
    """
    model = models.Gaussian2D(x_stddev=1, y_stddev=1)

    if 'x_stddev' in source_table.colnames:
        xstd = source_table['x_stddev']
    else:
        xstd = model.x_stddev.value  # default
    if 'y_stddev' in source_table.colnames:
        ystd = source_table['y_stddev']
    else:
        ystd = model.y_stddev.value  # default

    colnames = source_table.colnames
    if 'flux' in colnames and 'amplitude' not in colnames:
        source_table = source_table.copy()
        source_table['amplitude'] = (source_table['flux']
                                     / (2.0 * np.pi * xstd * ystd))

    return make_model_sources_image(shape, model, source_table,
                                    oversample=oversample)


def make_gaussian_prf_sources_image(shape, source_table):
    r"""
    Make an image containing 2D Gaussian sources.

    Parameters
    ----------
    shape : 2-tuple of int
        The shape of the output 2D image.

    source_table : `~astropy.table.Table`
        Table of parameters for the Gaussian sources.  Each row of the
        table corresponds to a Gaussian source whose parameters are
        defined by the column names.  With the exception of ``'flux'``,
        column names that do not match model parameters will be ignored
        (flux will be converted to amplitude).  If both ``'flux'`` and
        ``'amplitude'`` are present, then ``'flux'`` will be ignored.
        Model parameters not defined in the table will be set to the
        default value.

    Returns
    -------
    image : 2D `~numpy.ndarray`
        Image containing 2D Gaussian sources.

    See Also
    --------
    make_model_sources_image, make_random_gaussians_table

    Examples
    --------
    .. plot::
        :include-source:

        import matplotlib.pyplot as plt
        from astropy.table import QTable
        from photutils.datasets import (make_gaussian_prf_sources_image,
                                        make_noise_image)

        # make a table of Gaussian sources
        table = QTable()
        table['amplitude'] = [50, 70, 150, 210]
        table['x_0'] = [160, 25, 150, 90]
        table['y_0'] = [70, 40, 25, 60]
        table['sigma'] = [15.2, 5.1, 3., 8.1]

        # make an image of the sources without noise, with Gaussian
        # noise, and with Poisson noise
        shape = (100, 200)
        image1 = make_gaussian_prf_sources_image(shape, table)
        image2 = (image1 + make_noise_image(shape, distribution='gaussian',
                                            mean=5., stddev=5.))
        image3 = (image1 + make_noise_image(shape, distribution='poisson',
                                            mean=5.))

        # plot the images
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(8, 12))
        ax1.imshow(image1, origin='lower', interpolation='nearest')
        ax1.set_title('Original image')
        ax2.imshow(image2, origin='lower', interpolation='nearest')
        ax2.set_title('Original image with added Gaussian noise'
                      r' ($\mu = 5, \sigma = 5$)')
        ax3.imshow(image3, origin='lower', interpolation='nearest')
        ax3.set_title(r'Original image with added Poisson noise ($\mu = 5$)')
    """
    model = IntegratedGaussianPRF(sigma=1)

    if 'sigma' in source_table.colnames:
        sigma = source_table['sigma']
    else:
        sigma = model.sigma.value  # default

    colnames = source_table.colnames
    if 'flux' not in colnames and 'amplitude' in colnames:
        source_table = source_table.copy()
        source_table['flux'] = (source_table['amplitude']
                                * (2.0 * np.pi * sigma * sigma))

    return make_model_sources_image(shape, model, source_table,
                                    oversample=1)


def make_4gaussians_image(noise=True):
    """
    Make an example image containing four 2D Gaussians plus a constant
    background.

    The background has a mean of 5.

    If ``noise`` is `True`, then Gaussian noise with a mean of 0 and a
    standard deviation of 5 is added to the output image.

    Parameters
    ----------
    noise : bool, optional
        Whether to include noise in the output image (default is
        `True`).

    Returns
    -------
    image : 2D `~numpy.ndarray`
        Image containing four 2D Gaussian sources.

    See Also
    --------
    make_100gaussians_image

    Examples
    --------
    .. plot::
        :include-source:

        import matplotlib.pyplot as plt
        from photutils.datasets import make_4gaussians_image

        image = make_4gaussians_image()
        plt.imshow(image, origin='lower', interpolation='nearest')
    """
    table = QTable()
    table['amplitude'] = [50, 70, 150, 210]
    table['x_mean'] = [160, 25, 150, 90]
    table['y_mean'] = [70, 40, 25, 60]
    table['x_stddev'] = [15.2, 5.1, 3.0, 8.1]
    table['y_stddev'] = [2.6, 2.5, 3.0, 4.7]
    table['theta'] = np.radians(np.array([145.0, 20.0, 0.0, 60.0]))

    shape = (100, 200)
    data = make_gaussian_sources_image(shape, table) + 5.0

    if noise:
        rng = np.random.RandomState(12345)
        data += rng.normal(loc=0.0, scale=5.0, size=shape)

    return data


def make_100gaussians_image(noise=True):
    """
    Make an example image containing 100 2D Gaussians plus a constant
    background.

    The background has a mean of 5.

    If ``noise`` is `True`, then Gaussian noise with a mean of 0 and a
    standard deviation of 2 is added to the output image.

    Parameters
    ----------
    noise : bool, optional
        Whether to include noise in the output image (default is
        `True`).

    Returns
    -------
    image : 2D `~numpy.ndarray`
        Image containing 100 2D Gaussian sources.

    See Also
    --------
    make_4gaussians_image

    Examples
    --------
    .. plot::
        :include-source:

        import matplotlib.pyplot as plt
        from photutils.datasets import make_100gaussians_image

        image = make_100gaussians_image()
        plt.imshow(image, origin='lower', interpolation='nearest')
    """
    n_sources = 100
    flux_range = [500, 1000]
    xmean_range = [0, 500]
    ymean_range = [0, 300]
    xstddev_range = [1, 5]
    ystddev_range = [1, 5]
    params = {'flux': flux_range,
              'x_mean': xmean_range,
              'y_mean': ymean_range,
              'x_stddev': xstddev_range,
              'y_stddev': ystddev_range,
              'theta': [0, 2 * np.pi]}

    rng = np.random.RandomState(12345)
    sources = QTable()
    for param_name, (lower, upper) in params.items():
        # Generate a column for every item in param_ranges, even if it
        # is not in the model (e.g., flux).  However, such columns will
        # be ignored when rendering the image.
        sources[param_name] = rng.uniform(lower, upper, n_sources)
    xstd = sources['x_stddev']
    ystd = sources['y_stddev']
    sources['amplitude'] = sources['flux'] / (2.0 * np.pi * xstd * ystd)

    shape = (300, 500)
    data = make_gaussian_sources_image(shape, sources) + 5.0

    if noise:
        rng = np.random.RandomState(12345)
        data += rng.normal(loc=0.0, scale=2.0, size=shape)

    return data


def _define_psf_shape(psf_model, psf_shape):
    """
    Define the shape of the model to evaluate, including the
    oversampling.
    """
    try:
        model_ndim = psf_model.data.ndim
    except AttributeError:
        model_ndim = None

    try:
        model_bbox = psf_model.bounding_box
    except NotImplementedError:
        model_bbox = None

    if model_ndim is not None:
        if model_ndim == 3:
            model_shape = psf_model.data.shape[1:]
        elif model_ndim == 2:
            model_shape = psf_model.data.shape

        try:
            oversampling = psf_model.oversampling
        except AttributeError:
            oversampling = 1
        oversampling = as_pair('oversampling', oversampling)

        model_shape = tuple(np.array(model_shape) // oversampling)

        if np.any(psf_shape > model_shape):
            psf_shape = tuple(np.min([model_shape, psf_shape], axis=0))
            warnings.warn('The input psf_shape is larger than the size of the '
                          'evaluated PSF model (including oversampling). The '
                          f'psf_shape was changed to {psf_shape!r}.',
                          AstropyUserWarning)

    elif model_bbox is not None:
        ixmin = math.floor(model_bbox['x'].lower + 0.5)
        ixmax = math.ceil(model_bbox['x'].upper + 0.5)
        iymin = math.floor(model_bbox['y'].lower + 0.5)
        iymax = math.ceil(model_bbox['y'].upper + 0.5)
        model_shape = (iymax - iymin, ixmax - ixmin)

        if np.any(psf_shape > model_shape):
            psf_shape = tuple(np.min([model_shape, psf_shape], axis=0))
            warnings.warn('The input psf_shape is larger than the bounding '
                          'box size of the PSF model. The psf_shape was '
                          f'changed to {psf_shape!r}.', AstropyUserWarning)

    return psf_shape


def make_test_psf_data(shape, psf_model, psf_shape, nsources, *,
                       flux_range=(100, 1000), min_separation=1, seed=0,
                       border_size=None, progress_bar=False):
    """
    Make an example image containing PSF model images.

    Source positions and fluxes are randomly generated using an optional
    ``seed``.

    Parameters
    ----------
    shape : 2-tuple of int
        The shape of the output image.

    psf_model : `astropy.modeling.Fittable2DModel`
        The PSF model.

    psf_shape : 2-tuple of int
        The shape around the center of the star that will used to
        evaluate the ``psf_model``.

    nsources : int
        The number of sources to generate.

    flux_range : tuple, optional
        The lower and upper bounds of the flux range.

    min_separation : float, optional
        The minimum separation between the centers of two sources. Note
        that if the minimum separation is too large, the number of
        sources generated may be less than ``nsources``.

    seed : int, optional
        A seed to initialize the `numpy.random.BitGenerator`. If `None`,
        then fresh, unpredictable entropy will be pulled from the OS.

    border_size : tuple of 2 int, optional
        The (ny, nx) size of the border around the image where no
        sources will be generated (i.e., the source center will not be
        located within the border). If `None`, then a border size equal
        to half the (y, x) size of the evaluated PSF model (i.e., taking
        into account oversampling) will be used.

    progress_bar : bool, optional
        Whether to display a progress bar when creating the sources. The
        progress bar requires that the `tqdm <https://tqdm.github.io/>`_
        optional dependency be installed. Note that the progress
        bar does not currently work in the Jupyter console due to
        limitations in ``tqdm``.

    Returns
    -------
    data : 2D `~numpy.ndarray`
        The simulated image.

    table : `~astropy.table.Table`
        A table containing the parameters of the generated sources.
    """
    psf_shape = _define_psf_shape(psf_model, psf_shape)

    if border_size is None:
        hshape = (np.array(psf_shape) - 1) // 2
    else:
        hshape = border_size
    xrange = (hshape[1], shape[1] - hshape[1])
    yrange = (hshape[0], shape[0] - hshape[0])

    xycoords = make_random_xycoords(nsources, xrange, yrange,
                                    min_separation=min_separation,
                                    seed=seed)
    x, y = np.transpose(xycoords)

    rng = np.random.default_rng(seed)
    flux = rng.uniform(flux_range[0], flux_range[1], nsources)
    flux = flux[:len(x)]

    sources = QTable()
    sources['x_0'] = x
    sources['y_0'] = y
    sources['flux'] = flux

    sources_iter = sources
    if progress_bar:  # pragma: no cover
        desc = 'Adding sources'
        sources_iter = add_progress_bar(sources, desc=desc)

    data = np.zeros(shape, dtype=float)
    for source in sources_iter:
        for param in ('x_0', 'y_0', 'flux'):
            setattr(psf_model, param, source[param])
        xcen = source['x_0']
        ycen = source['y_0']
        slc_lg, _ = overlap_slices(shape, psf_shape, (ycen, xcen), mode='trim')
        yy, xx = np.mgrid[slc_lg]
        data[slc_lg] += psf_model(xx, yy)

    sources.rename_column('x_0', 'x')
    sources.rename_column('y_0', 'y')
    sources.rename_column('flux', 'flux')

    return data, sources
