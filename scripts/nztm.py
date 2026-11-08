"""NZTM2000 (EPSG:2193) <-> NZGD2000 lon/lat in plain numpy, so the model
runs where PROJ isn't available (the browser). Transverse Mercator on GRS80
with Krüger's series to the 6th order: well under a millimetre within New
Zealand. NZGD2000 and WGS84 are treated as the same (they differ by
centimetres).
"""
import numpy as np

A = 6378137.0
F = 1 / 298.257222101            # GRS80
K0 = 0.9996
LON0 = np.radians(173.0)
FE, FN = 1_600_000.0, 10_000_000.0

_n = F / (2 - F)
_A = A / (1 + _n) * (1 + _n**2 / 4 + _n**4 / 64 + _n**6 / 256)
_alpha = [
    _n / 2 - 2 * _n**2 / 3 + 5 * _n**3 / 16 + 41 * _n**4 / 180 - 127 * _n**5 / 288 + 7891 * _n**6 / 37800,
    13 * _n**2 / 48 - 3 * _n**3 / 5 + 557 * _n**4 / 1440 + 281 * _n**5 / 630 - 1983433 * _n**6 / 1935360,
    61 * _n**3 / 240 - 103 * _n**4 / 140 + 15061 * _n**5 / 26880 + 167603 * _n**6 / 181440,
    49561 * _n**4 / 161280 - 179 * _n**5 / 168 + 6601661 * _n**6 / 7257600,
    34729 * _n**5 / 80640 - 3418889 * _n**6 / 1995840,
    212378941 * _n**6 / 319334400,
]
_beta = [
    _n / 2 - 2 * _n**2 / 3 + 37 * _n**3 / 96 - _n**4 / 360 - 81 * _n**5 / 512 + 96199 * _n**6 / 604800,
    _n**2 / 48 + _n**3 / 15 - 437 * _n**4 / 1440 + 46 * _n**5 / 105 - 1118711 * _n**6 / 3870720,
    17 * _n**3 / 480 - 37 * _n**4 / 840 - 209 * _n**5 / 4480 + 5569 * _n**6 / 90720,
    4397 * _n**4 / 161280 - 11 * _n**5 / 504 - 830251 * _n**6 / 7257600,
    4583 * _n**5 / 161280 - 108847 * _n**6 / 3991680,
    20648693 * _n**6 / 638668800,
]
_e = np.sqrt(F * (2 - F))


def to_nztm(lon, lat):
    """lon/lat in degrees -> NZTM easting, northing in metres."""
    lon, lat = np.radians(np.asarray(lon, float)), np.radians(np.asarray(lat, float))
    t = np.sinh(np.arctanh(np.sin(lat)) - _e * np.arctanh(_e * np.sin(lat)))
    dl = lon - LON0
    xi = np.arctan2(t, np.cos(dl))
    eta = np.arctanh(np.sin(dl) / np.sqrt(1 + t * t))
    x, y = eta.copy(), xi.copy()
    for j, a in enumerate(_alpha, 1):
        x += a * np.cos(2 * j * xi) * np.sinh(2 * j * eta)
        y += a * np.sin(2 * j * xi) * np.cosh(2 * j * eta)
    return FE + K0 * _A * x, FN + K0 * _A * y


def from_nztm(x, y):
    """NZTM easting, northing in metres -> lon/lat in degrees."""
    xi = (np.asarray(y, float) - FN) / (K0 * _A)
    eta = (np.asarray(x, float) - FE) / (K0 * _A)
    xp, ep = xi.copy(), eta.copy()
    for j, b in enumerate(_beta, 1):
        xp -= b * np.sin(2 * j * xi) * np.cosh(2 * j * eta)
        ep -= b * np.cos(2 * j * xi) * np.sinh(2 * j * eta)
    chi = np.arcsin(np.sin(xp) / np.cosh(ep))
    lon = LON0 + np.arctan2(np.sinh(ep), np.cos(xp))
    # conformal latitude -> geodetic latitude (Newton on tan)
    tau_p = np.tan(chi)
    tau = tau_p.copy()
    for _ in range(5):
        s = tau / np.sqrt(1 + tau * tau)
        sig = np.sinh(_e * np.arctanh(_e * s))
        tp = tau * np.sqrt(1 + sig * sig) - sig * np.sqrt(1 + tau * tau)
        dtau = (tau_p - tp) / np.sqrt(1 + tp * tp) * (1 + (1 - _e**2) * tau * tau) / (
            (1 - _e**2) * np.sqrt(1 + tau * tau))
        tau = tau + dtau
    return np.degrees(lon), np.degrees(np.arctan(tau))


def geom_to_nztm(g):
    """A shapely geometry in lon/lat -> NZTM."""
    import shapely
    return shapely.transform(g, lambda c: np.column_stack(to_nztm(c[:, 0], c[:, 1])))


def geom_from_nztm(g):
    import shapely
    return shapely.transform(g, lambda c: np.column_stack(from_nztm(c[:, 0], c[:, 1])))
