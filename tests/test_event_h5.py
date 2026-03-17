#-*- coding: utf-8 -*-
"""Tests for modern .nxs.h5 event NeXus file support (Phases 1-3)."""
import pytest
import os

H5_REF_M = '/SNS/REF_M/IPTS-9801/nexus/REF_M_29750.nxs.h5'
H5_REF_M_HISTO = '/SNS/REF_M/IPTS-9801/data/REF_M_29750_histo.nxs'
H5_REF_M_NOLAMDA = '/SNS/REF_M/IPTS-16196/nexus/REF_M_29015.nxs.h5'
H5_REF_L = '/SNS/REF_L/IPTS-36119/nexus/REF_L_220030.nxs.h5'


# ── Phase 1: Helper functions ──────────────────────────────────────────

@pytest.mark.skipif(not os.path.exists(H5_REF_M), reason='No access to SNS data')
class TestGetDetectorDimensions:
    def test_ref_m_dimensions(self):
        import h5py
        from quicknxs.qreduce import _get_detector_dimensions
        with h5py.File(H5_REF_M, 'r') as f:
            n_x, n_y = _get_detector_dimensions(f['entry'])
        assert n_x == 304
        assert n_y == 256

    @pytest.mark.skipif(not os.path.exists(H5_REF_L), reason='No access to REF_L data')
    def test_ref_l_dimensions(self):
        import h5py
        from quicknxs.qreduce import _get_detector_dimensions
        with h5py.File(H5_REF_L, 'r') as f:
            n_x, n_y = _get_detector_dimensions(f['entry'])
        assert n_x == 256
        assert n_y == 304


@pytest.mark.skipif(not os.path.exists(H5_REF_M), reason='No access to SNS data')
class TestGetDaslogValue:
    def test_ref_m_dangle(self):
        import h5py
        from quicknxs.qreduce import _get_daslog_value
        with h5py.File(H5_REF_M, 'r') as f:
            dangle = _get_daslog_value(f['entry'], 'DANGLE')
        assert abs(dangle - 15.005) < 0.01

    def test_ref_m_sangle(self):
        import h5py
        from quicknxs.qreduce import _get_daslog_value
        with h5py.File(H5_REF_M, 'r') as f:
            sangle = _get_daslog_value(f['entry'], 'SANGLE')
        assert abs(sangle - 0.332) < 0.01

    @pytest.mark.skipif(not os.path.exists(H5_REF_L), reason='No access to REF_L data')
    def test_ref_l_ths(self):
        import h5py
        from quicknxs.qreduce import _get_daslog_value
        with h5py.File(H5_REF_L, 'r') as f:
            ths = _get_daslog_value(f['entry'], 'ths')
        assert abs(ths - 2.101) < 0.01

    def test_missing_key_with_default(self):
        import h5py
        from quicknxs.qreduce import _get_daslog_value
        with h5py.File(H5_REF_M, 'r') as f:
            val = _get_daslog_value(f['entry'], 'NONEXISTENT', default=42.0)
        assert val == 42.0

    def test_missing_key_with_fallback(self):
        import h5py
        from quicknxs.qreduce import _get_daslog_value
        with h5py.File(H5_REF_M, 'r') as f:
            val = _get_daslog_value(f['entry'], 'NONEXISTENT',
                                   fallback_key='DANGLE')
        assert abs(val - 15.005) < 0.01

    def test_missing_key_raises(self):
        import h5py
        from quicknxs.qreduce import _get_daslog_value
        with h5py.File(H5_REF_M, 'r') as f:
            with pytest.raises(KeyError):
                _get_daslog_value(f['entry'], 'NONEXISTENT')


@pytest.mark.skipif(not os.path.exists(H5_REF_M), reason='No access to SNS data')
class TestReadInstrumentSettings:
    def test_ref_m_settings(self):
        import h5py
        from quicknxs.qreduce import _read_instrument_settings
        with h5py.File(H5_REF_M, 'r') as f:
            settings = _read_instrument_settings('ref_m', f['entry'])
        assert settings['number-of-x-pixels'] == 304
        assert settings['number-of-y-pixels'] == 256
        assert settings['pixel-width'] == 0.70

    @pytest.mark.skipif(not os.path.exists(H5_REF_L), reason='No access to REF_L data')
    def test_ref_l_settings(self):
        import h5py
        from quicknxs.qreduce import _read_instrument_settings
        with h5py.File(H5_REF_L, 'r') as f:
            settings = _read_instrument_settings('ref_l', f['entry'])
        assert settings['number-of-x-pixels'] == 256
        assert settings['number-of-y-pixels'] == 304
        assert settings['sample-det-distance'] > 0


class TestDecode:
    def test_bytes_input(self):
        from quicknxs.qreduce import _decode
        assert _decode(b'hello') == 'hello'

    def test_str_input(self):
        from quicknxs.qreduce import _decode
        assert _decode('hello') == 'hello'


# ── Phase 2: Metadata extraction ──────────────────────────────────────

@pytest.mark.skipif(not os.path.exists(H5_REF_M), reason='No access to SNS data')
class TestMRDatasetCollectInfoH5:
    def test_metadata_extraction(self):
        import h5py
        from quicknxs.qreduce import MRDataset
        with h5py.File(H5_REF_M, 'r') as f:
            ds = MRDataset()
            ds._collect_info_h5(f['entry'])
        assert abs(ds.dangle - 15.005) < 0.01
        assert abs(ds.sangle - 0.332) < 0.01
        assert ds.proton_charge > 0
        assert ds.total_counts == 19195
        assert ds.number == 29750
        assert ds.experiment == 'IPTS-9801'
        assert ds.dist_sam_det > 0
        assert ds.dist_mod_det > ds.dist_sam_det
        assert ds.slit1_width > 0
        assert ds.det_size_x > 0
        assert ds.det_size_y > 0

    def test_logs_populated(self):
        import h5py
        from quicknxs.qreduce import MRDataset
        with h5py.File(H5_REF_M, 'r') as f:
            ds = MRDataset()
            ds._collect_info_h5(f['entry'])
        assert len(ds.logs) > 0
        assert 'DANGLE' in ds.logs


@pytest.mark.skipif(not os.path.exists(H5_REF_L), reason='No access to REF_L data')
class TestLRDatasetCollectInfoH5:
    def test_metadata_extraction(self):
        import h5py
        from quicknxs.qreduce import LRDataset
        with h5py.File(H5_REF_L, 'r') as f:
            ds = LRDataset()
            ds._collect_info_h5(f['entry'])
        assert abs(ds.sangle - 2.101) < 0.01   # ths
        assert abs(ds.dangle - 4.201) < 0.01   # tthd (detector arm 2θ)
        assert abs(ds.thi - (-0.007)) < 0.01   # incident angle stored separately
        assert ds.dangle0 == 0.0
        assert ds.proton_charge > 0
        assert ds.total_counts == 85387
        assert ds.number == 220030
        assert ds.dist_sam_det > 0
        assert ds.lambda_center > 0


# ── Phase 3: Core event-to-histogram conversion ──────────────────────

@pytest.mark.skipif(not os.path.exists(H5_REF_M), reason='No access to SNS data')
class TestFormatDetection:
    def test_detects_event_h5_format(self):
        import h5py
        with h5py.File(H5_REF_M, 'r') as f:
            first_entry = list(f.keys())[0]
            def_raw = f[first_entry]['definition'][()][0]
            definition = def_raw.decode('utf-8') if isinstance(def_raw, bytes) else str(def_raw)
        assert definition == 'NXsnsevent'


@pytest.mark.skipif(not os.path.exists(H5_REF_M), reason='No access to SNS data')
class TestFromEventH5:
    def test_ref_m_load(self):
        from quicknxs.qreduce import NXSData
        data = NXSData(H5_REF_M, use_caching=False)
        assert data is not None
        assert len(data) >= 1
        ds = data[0]
        # Verify 3D histogram was created
        assert ds.data is not None
        assert len(ds.data.shape) == 3
        assert ds.data.shape[0] == 304  # n_x for REF_M
        assert ds.data.shape[1] == 256  # n_y for REF_M
        # Verify projections
        assert ds.xydata is not None
        assert ds.xydata.shape == (256, 304)  # transposed
        assert ds.xtofdata is not None
        assert ds.xtofdata.shape[0] == 304
        # Total counts in histogram should match event count
        assert abs(ds.data.sum() - ds.total_counts) < 2
        # Verify tof_edges
        assert ds.tof_edges is not None
        assert len(ds.tof_edges) > 1
        # Verify event mode flag
        assert ds.from_event_mode is True
        # Verify measurement type
        assert data.measurement_type == 'Unpolarized'

    @pytest.mark.skipif(not os.path.exists(H5_REF_M_HISTO),
                        reason='No access to SNS data')
    def test_ref_m_matches_histo(self):
        """Compare event-binned XY projection against known-good histo data"""
        import numpy as np
        from quicknxs.qreduce import NXSData
        h5_data = NXSData(H5_REF_M, use_caching=False)
        assert h5_data is not None
        h5_xy = h5_data[0].xydata
        histo_data = NXSData(H5_REF_M_HISTO, use_caching=False)
        assert histo_data is not None
        histo_xy = histo_data[0].xydata
        # Compare: correlation > 0.999
        corr = np.corrcoef(h5_xy.ravel(), histo_xy.ravel())[0, 1]
        assert corr > 0.999, f'XY correlation {corr:.6f} too low'
        # Max per-pixel difference should be small
        diff = np.abs(h5_xy - histo_xy)
        assert diff.max() < 10, f'Max pixel diff {diff.max()} too large'

    @pytest.mark.skipif(not os.path.exists(H5_REF_L),
                        reason='No access to REF_L data')
    def test_ref_l_load(self):
        from quicknxs.qreduce import NXSData
        data = NXSData(H5_REF_L, use_caching=False)
        assert data is not None
        assert len(data) >= 1
        ds = data[0]
        assert ds.data.shape[0] == 256  # n_x for REF_L
        assert ds.data.shape[1] == 304  # n_y for REF_L
        assert ds.xydata.shape == (304, 256)  # transposed
        # Not all events fall within the ±1.6 Å TOF window — check reasonable fraction
        assert ds.data.sum() > 0
        assert ds.data.sum() <= ds.total_counts
        assert ds.from_event_mode is True
        assert abs(ds.sangle - 2.101) < 0.01
        assert abs(ds.dangle - 4.201) < 0.01   # tthd, NOT thi
        assert abs(ds.thi - (-0.007)) < 0.01   # incident angle stored separately
        assert abs(ds.lambda_center - 6.2) < 0.1

    @pytest.mark.skipif(not os.path.exists(H5_REF_M_NOLAMDA),
                        reason='No access to SNS data')
    def test_ref_m_missing_lambda_graceful(self):
        """Early commissioning files lack LambdaRequest — should use default"""
        from quicknxs.qreduce import NXSData
        data = NXSData(H5_REF_M_NOLAMDA, use_caching=False)
        assert data is not None
        ds = data[0]
        assert ds.lambda_center == 3.37  # default fallback
        assert ds.data is not None
        assert ds.total_counts == 14863
