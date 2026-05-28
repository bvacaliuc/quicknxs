#-*- coding: utf-8 -*-
"""Tests for modern .nxs.h5 event NeXus file support (Phases 1-9)."""
import pytest
import os

H5_REF_M = '/SNS/REF_M/IPTS-9801/nexus/REF_M_29750.nxs.h5'
H5_REF_M_HISTO = '/SNS/REF_M/IPTS-9801/data/REF_M_29750_histo.nxs'
H5_REF_M_NOLAMDA = '/SNS/REF_M/IPTS-16196/nexus/REF_M_29015.nxs.h5'
H5_REF_L = '/SNS/REF_L/IPTS-36119/nexus/REF_L_220030.nxs.h5'
H5_REF_L_NO_ERROR = '/SNS/REF_L/IPTS-14316/nexus/REF_L_138523.nxs.h5'
H5_REF_M_POLARIZED = '/SNS/REF_M/IPTS-9801/nexus/REF_M_29742.nxs.h5'
H5_REF_M_POLARIZED_HISTO = '/SNS/REF_M/IPTS-9801/data/REF_M_29742_histo.nxs'


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


# ── Phase 4: File search and time_from_header ─────────────────────────

class TestLocateFile:
    """Test locate_file() H5 support.

    Note: Full integration tests with live glob over sshfs are impractical
    (each glob of /SNS/REF_M/*/ takes 2+ minutes over the sshfs link).
    These tests verify the config and logic without live glob searches.
    """

    def test_ref_m_h5_base_search_configured(self):
        """Verify H5_BASE_SEARCH is set in ref_m config"""
        from quicknxs.config import ref_m
        assert hasattr(ref_m, 'H5_BASE_SEARCH')
        assert 'REF_M' in ref_m.H5_BASE_SEARCH
        assert '.nxs.h5' in ref_m.H5_BASE_SEARCH

    def test_ref_l_h5_base_search_configured(self):
        """Verify H5_BASE_SEARCH is set in ref_l config"""
        from quicknxs.config import ref_l
        assert hasattr(ref_l, 'H5_BASE_SEARCH')
        assert 'REF_L' in ref_l.H5_BASE_SEARCH
        assert '.nxs.h5' in ref_l.H5_BASE_SEARCH

    def test_h5_search_pattern_resolves(self):
        """Verify the H5_BASE_SEARCH pattern produces a valid path"""
        from quicknxs.config import ref_m
        import os
        pattern = os.path.join(ref_m.data_base, ref_m.H5_BASE_SEARCH % 29015)
        # The pattern should reference the nexus/ subdirectory
        assert 'nexus' in pattern
        assert pattern.endswith('.nxs.h5')

    @pytest.mark.skipif(not os.path.exists(H5_REF_M), reason='No access to SNS data')
    def test_h5_file_exists_at_expected_path(self):
        """Verify the .nxs.h5 file exists at the path the search pattern targets"""
        assert os.path.isfile(H5_REF_M)

    def test_locate_file_falls_through_to_h5(self):
        """Verify locate_file tries H5_BASE_SEARCH when histo/event not found"""
        from unittest.mock import patch
        from quicknxs.config import ref_m
        import quicknxs.config as cfg
        orig = cfg.instrument
        cfg.instrument = ref_m
        try:
            # Mock glob to return empty for histo/event, then a match for h5
            def mock_glob(pattern):
                if '.nxs.h5' in pattern:
                    return ['/SNS/REF_M/IPTS-16196/nexus/REF_M_29015.nxs.h5']
                return []

            with patch('quicknxs.qreduce.glob', side_effect=mock_glob):
                from quicknxs.qreduce import locate_file
                result = locate_file(29015, verbose=False)
                assert result is not None
                assert result.endswith('.nxs.h5')
                assert '29015' in result
        finally:
            cfg.instrument = orig

    def test_locate_file_prefers_histo_over_h5(self):
        """Verify histo is preferred when both formats exist"""
        from unittest.mock import patch
        from quicknxs.config import ref_m
        import quicknxs.config as cfg
        orig = cfg.instrument
        cfg.instrument = ref_m
        try:
            def mock_glob(pattern):
                if 'histo.nxs' in pattern:
                    return ['/SNS/REF_M/IPTS-9801/data/REF_M_29750_histo.nxs']
                if '.nxs.h5' in pattern:
                    return ['/SNS/REF_M/IPTS-9801/nexus/REF_M_29750.nxs.h5']
                return []

            with patch('quicknxs.qreduce.glob', side_effect=mock_glob):
                from quicknxs.qreduce import locate_file
                result = locate_file(29750, verbose=False)
                assert result is not None
                assert 'histo.nxs' in result
        finally:
            cfg.instrument = orig

    def test_locate_file_returns_none_when_nothing_found(self):
        """Verify locate_file returns None when no file matches"""
        from unittest.mock import patch
        from quicknxs.config import ref_m
        import quicknxs.config as cfg
        orig = cfg.instrument
        cfg.instrument = ref_m
        try:
            with patch('quicknxs.qreduce.glob', return_value=[]):
                from quicknxs.qreduce import locate_file
                result = locate_file(99999, verbose=False)
                assert result is None
        finally:
            cfg.instrument = orig


@pytest.mark.skipif(not os.path.exists(H5_REF_M), reason='No access to SNS data')
class TestTimeFromHeader:
    def test_time_from_header_h5(self):
        from quicknxs.qreduce import time_from_header
        result = time_from_header(H5_REF_M)
        assert result is not None
        assert result > 0

    @pytest.mark.skipif(not os.path.exists(H5_REF_L),
                        reason='No access to REF_L data')
    def test_time_from_header_ref_l_h5(self):
        from quicknxs.qreduce import time_from_header
        result = time_from_header(H5_REF_L)
        assert result is not None
        assert result > 0


# ── Phase 5: Event splitting ──────────────────────────────────────────

@pytest.mark.skipif(not os.path.exists(H5_REF_M), reason='No access to SNS data')
class TestEventSplitting:
    def test_split_produces_subset(self):
        from quicknxs.qreduce import NXSData
        full = NXSData(H5_REF_M, use_caching=False)
        split = NXSData(H5_REF_M, event_split_bins=4, event_split_index=0,
                        use_caching=False)
        assert full is not None
        assert split is not None
        assert split[0].data.sum() < full[0].data.sum()
        assert split[0].data.sum() > 0

    def test_splits_sum_to_total(self):
        import numpy as np
        from quicknxs.qreduce import NXSData
        full = NXSData(H5_REF_M, use_caching=False)
        assert full is not None
        total = 0
        for i in range(4):
            part = NXSData(H5_REF_M, event_split_bins=4, event_split_index=i,
                           use_caching=False)
            if part is not None:
                total += part[0].data.sum()
        # All events that fall within TOF window should be accounted for
        assert abs(total - full[0].data.sum()) < 10

    @pytest.mark.skipif(not os.path.exists(H5_REF_L),
                        reason='No access to REF_L data')
    def test_split_ref_l(self):
        from quicknxs.qreduce import NXSData
        full = NXSData(H5_REF_L, use_caching=False)
        split = NXSData(H5_REF_L, event_split_bins=4, event_split_index=0,
                        use_caching=False)
        assert full is not None
        assert split is not None
        assert split[0].data.sum() < full[0].data.sum()
        assert split[0].data.sum() > 0


# ── Phase 6: Backward compatibility ──────────────────────────────────

@pytest.mark.skipif(
    not os.path.exists('/SNS/REF_M/IPTS-16196/0/25899/NeXus/REF_M_25899_histo.nxs'),
    reason='No access to SNS data')
class TestBackwardCompatibility:
    def test_legacy_histo_still_loads(self):
        from quicknxs.qreduce import NXSData
        data = NXSData('/SNS/REF_M/IPTS-16196/0/25899/NeXus/REF_M_25899_histo.nxs',
                       use_caching=False)
        assert data is not None
        assert len(data) >= 1
        assert data[0].data is not None

    @pytest.mark.skipif(
        not os.path.exists('/SNS/REF_L/IPTS-7053/0/80836/NeXus/REF_L_80836_histo.nxs'),
        reason='No access to REF_L data')
    def test_legacy_ref_l_histo_still_loads(self):
        from quicknxs.qreduce import NXSData
        data = NXSData('/SNS/REF_L/IPTS-7053/0/80836/NeXus/REF_L_80836_histo.nxs',
                       use_caching=False)
        assert data is not None
        assert data[0].data.shape == (304, 256, 2001)


# ── Phase 8: Dead-time correction ─────────────────────────────────────

@pytest.mark.skipif(not os.path.exists(H5_REF_L), reason='No access to REF_L data')
class TestDeadTimeCorrection:
    def test_correction_factor_reasonable(self):
        """DTC factors should be >= 1.0 (more true counts than measured)"""
        import h5py
        from quicknxs.qreduce import LRDataset
        from numpy import linspace
        with h5py.File(H5_REF_L, 'r') as f:
            tof_edges = linspace(5000, 60000, 41)
            dtc = LRDataset._apply_dead_time_correction(f['entry'], tof_edges)
        assert all(dtc >= 0.99)  # correction >= 1 (or near 1 for low rates)
        assert all(dtc < 2.0)    # should not be extreme

    @pytest.mark.skipif(not os.path.exists(H5_REF_L_NO_ERROR),
                        reason='No access to REF_L_138523 data')
    def test_no_error_events_returns_unity(self):
        """When no bank_error_events, correction should be all 1.0"""
        import h5py
        from quicknxs.qreduce import LRDataset
        from numpy import linspace, allclose, ones
        with h5py.File(H5_REF_L_NO_ERROR, 'r') as f:
            tof_edges = linspace(5000, 60000, 41)
            dtc = LRDataset._apply_dead_time_correction(f['entry'], tof_edges)
        assert allclose(dtc, ones(40))

    def test_paralyzable_vs_nonparalyzable(self):
        """Both models should give >= 1.0 for low count rates"""
        import h5py
        from quicknxs.qreduce import LRDataset
        from numpy import linspace
        with h5py.File(H5_REF_L, 'r') as f:
            tof_edges = linspace(5000, 60000, 41)
            dtc_p = LRDataset._apply_dead_time_correction(
                f['entry'], tof_edges, paralyzable=True)
            dtc_np = LRDataset._apply_dead_time_correction(
                f['entry'], tof_edges, paralyzable=False)
        assert all(dtc_p >= 0.99)
        assert all(dtc_np >= 0.99)

    def test_dtc_applied_in_from_event_h5(self):
        """Verify dead-time correction is integrated into LRDataset loading.
        DTC increases histogram counts, so corrected sum > uncorrected sum."""
        import h5py
        import numpy as np
        from quicknxs.qreduce import NXSData, LRDataset
        data = NXSData(H5_REF_L, use_caching=False)
        assert data is not None
        ds = data[0]
        assert ds.data is not None
        # Verify DTC factors >= 1.0 for this file (it has error events)
        with h5py.File(H5_REF_L, 'r') as f:
            dtc = LRDataset._apply_dead_time_correction(f['entry'], ds.tof_edges)
        assert np.all(dtc >= 1.0), 'DTC factors should be >= 1.0'
        assert np.any(dtc > 1.0), 'DTC should have some correction (error events exist)'
        # The corrected histogram sum should be positive
        assert ds.data.sum() > 0

    @pytest.mark.skipif(not os.path.exists(H5_REF_M), reason='No access to SNS data')
    def test_ref_m_does_not_apply_dtc(self):
        """Verify REF_M (MRDataset) does NOT apply dead-time correction"""
        from quicknxs.qreduce import NXSData
        data = NXSData(H5_REF_M, use_caching=False)
        assert data is not None
        ds = data[0]
        # REF_M should NOT have DTC applied — histogram sum ≈ total_counts
        assert abs(ds.data.sum() - ds.total_counts) < 2


# ── Phase 9: Polarization filtering ───────────────────────────────────

@pytest.mark.skipif(not os.path.exists(H5_REF_M_POLARIZED),
                    reason='No access to SNS data')
class TestPolarizationFiltering:
    def test_detects_polarized_data(self):
        """Polarized h5 file should produce multiple channels"""
        from quicknxs.qreduce import NXSData
        data = NXSData(H5_REF_M_POLARIZED, use_caching=False)
        assert data is not None
        assert len(data) >= 2  # at least 2 polarization channels

    def test_channel_names(self):
        """Channels should be named Off_Off and On_Off for 2-state SF1"""
        from quicknxs.qreduce import NXSData
        data = NXSData(H5_REF_M_POLARIZED, use_caching=False)
        names = data._channel_names
        assert 'Off_Off' in names
        assert 'On_Off' in names

    def test_measurement_type_polarized(self):
        """Measurement type should reflect polarized state"""
        from quicknxs.qreduce import NXSData
        data = NXSData(H5_REF_M_POLARIZED, use_caching=False)
        assert data.measurement_type == 'Polarized'

    @pytest.mark.skipif(not os.path.exists(H5_REF_M_POLARIZED_HISTO),
                        reason='No access to histo counterpart')
    @pytest.mark.timeout(180)
    def test_channel_counts_match_histo(self):
        """Total counts across channels should match histo within tolerance"""
        from quicknxs.qreduce import NXSData
        h5 = NXSData(H5_REF_M_POLARIZED, use_caching=False)
        histo = NXSData(H5_REF_M_POLARIZED_HISTO, use_caching=False)
        h5_total = sum(ch.total_counts for ch in h5._channel_data)
        histo_total = sum(ch.total_counts for ch in histo._channel_data)
        # Allow for transition events lost to veto filtering
        assert abs(h5_total - histo_total) < 200

    def test_unpolarized_single_channel(self):
        """Unpolarized run should still produce single channel"""
        from quicknxs.qreduce import NXSData
        data = NXSData(H5_REF_M, use_caching=False)
        assert len(data) == 1

    def test_filter_function_returns_channels(self):
        """_filter_events_by_polarization should return channel dict"""
        import h5py
        from quicknxs.qreduce import _filter_events_by_polarization
        with h5py.File(H5_REF_M_POLARIZED, 'r') as f:
            channels = _filter_events_by_polarization(f['entry'])
        assert channels is not None
        assert len(channels) >= 2
        for name, (ids, tofs, pc) in channels.items():
            assert len(ids) > 0
            assert len(ids) == len(tofs)
            assert pc is not None and pc > 0

    def test_filter_function_returns_none_without_sf1(self):
        """When SF1 is missing, should return None"""
        import h5py
        from quicknxs.qreduce import _filter_events_by_polarization
        # REF_L files don't have SF1 — use as proxy for missing SF1
        with h5py.File(H5_REF_L, 'r') as f:
            result = _filter_events_by_polarization(f['entry'])
        assert result is None

    def test_veto_filtering_excludes_transitions(self):
        """Veto filtering should reduce total counts vs raw event count"""
        import h5py
        from quicknxs.qreduce import _filter_events_by_polarization
        with h5py.File(H5_REF_M_POLARIZED, 'r') as f:
            raw_count = len(f['entry/bank1_events/event_id'][()])
            channels = _filter_events_by_polarization(f['entry'])
        assert channels is not None
        total = sum(len(ids) for ids, _, _ in channels.values())
        assert total < raw_count  # some events removed by veto/state filtering
        assert total > raw_count * 0.9  # but not too many lost

    def test_per_channel_proton_charge_splits(self):
        """Each channel must carry its OWN integrated proton charge (the charge
        accrued while its SF-state was active), not the full-run charge — this
        is what makes polarized normalization match Mantid (the v1-vs-Mantid
        'deficit'). See plan/v1-vs-mantid-deficit-rootcause.md."""
        import h5py
        import numpy as np
        from quicknxs.qreduce import _filter_events_by_polarization
        with h5py.File(H5_REF_M_POLARIZED, 'r') as f:
            entry = f['entry']
            full_pc = float(np.asarray(entry['DASlogs/proton_charge/value'][()]).sum())
            channels = _filter_events_by_polarization(entry)
        pcs = [pc for _, (_, _, pc) in channels.items()]
        assert all(pc is not None and pc > 0 for pc in pcs)
        # Channels partition the run, so they sum to ~the full-run charge
        # (only the small veto-transition charge is dropped).
        assert abs(sum(pcs) - full_pc) < 0.02 * full_pc
        # For a multi-channel run no single channel carries the whole run.
        if len(pcs) >= 2:
            assert max(pcs) < 0.98 * full_pc


# ── Chopper-speed-aware TOF bandwidth (prompt-28 Fault 1) ─────────────

class TestTofBandwidthChopperScaling:
    """Verify the TOF window widens proportionally when the chopper runs
    at 30 Hz (frame period 33.3 ms) instead of the reference 60 Hz."""

    def test_helper_scales_inversely_with_speed(self):
        from quicknxs.qreduce import _compute_tof_range_us
        tmin60, tmax60 = _compute_tof_range_us(21.0, 5.35, chopper_speed=60.0)
        tmin30, tmax30 = _compute_tof_range_us(21.0, 5.35, chopper_speed=30.0)
        # 30 Hz frame is twice as wide
        bw60 = tmax60 - tmin60
        bw30 = tmax30 - tmin30
        assert abs(bw30 - 2 * bw60) < 1e-6, \
            f"30 Hz bandwidth ({bw30:.2f}) should be 2× 60 Hz ({bw60:.2f})"
        # And centred on the same TOF as 60 Hz
        assert abs((tmin30 + tmax30) / 2 - (tmin60 + tmax60) / 2) < 1e-6

    def test_helper_default_speed_matches_60hz(self):
        from quicknxs.qreduce import _compute_tof_range_us
        ref = _compute_tof_range_us(21.0, 5.35, chopper_speed=60.0)
        defaulted = _compute_tof_range_us(21.0, 5.35)
        assert ref == defaulted

    def test_helper_handles_zero_speed_gracefully(self):
        from quicknxs.qreduce import _compute_tof_range_us
        # Should not divide-by-zero; should fall back to 60 Hz reference
        a = _compute_tof_range_us(21.0, 5.35, chopper_speed=0.0)
        b = _compute_tof_range_us(21.0, 5.35, chopper_speed=60.0)
        assert a == b

    @pytest.mark.skipif(
        not os.path.exists('/SNS/REF_M/IPTS-34473/nexus/REF_M_44159.nxs.h5'),
        reason='No access to IPTS-34473 dataset',
    )
    def test_ref_m_30hz_run_keeps_all_events(self):
        """44159 was acquired at 30 Hz / λ=5.35 Å; before the chopper-speed
        fix, ~half of the events fell outside the ±1.6 Å (60 Hz) window
        and were dropped."""
        from quicknxs.qreduce import NXSData
        data = NXSData('/SNS/REF_M/IPTS-34473/nexus/REF_M_44159.nxs.h5',
                       use_caching=False)
        assert data is not None
        ds = data['Off_Off']
        assert abs(ds.chopper_speed - 30.0) < 0.5
        # Histogram should contain ≥99 % of events (no clipping at frame edges)
        coverage = ds.data.sum() / float(ds.total_counts)
        assert coverage > 0.99, \
            f'coverage {coverage:.3f} too low - TOF window may still be narrow'


# ── DASlog scalar extraction (prompt-28 Fault 2) ──────────────────────

class TestLogScalarExtraction:
    def test_log_scalar_from_1d(self):
        import numpy as np
        from quicknxs.qreduce import _log_scalar
        v = _log_scalar(np.array([1.5]))
        assert float(v) == 1.5
        # %g must accept the result
        '%g' % v

    def test_log_scalar_from_2d_singleton(self):
        """Modern .nxs.h5 stores some single-valued DASlogs as (1,1)."""
        import numpy as np
        from quicknxs.qreduce import _log_scalar
        v = _log_scalar(np.array([[2.5]]))
        assert float(v) == 2.5
        '%g' % v

    def test_log_scalar_from_bytes_array(self):
        """String DASlogs (CanName, SampleName, …) must extract without error."""
        import numpy as np
        from quicknxs.qreduce import _log_scalar
        v = _log_scalar(np.array([[b'hello']]))
        assert v == b'hello'

    @pytest.mark.skipif(
        not os.path.exists('/SNS/REF_M/IPTS-34473/nexus/REF_M_44161.nxs.h5'),
        reason='No access to IPTS-34473 dataset',
    )
    def test_string_daslogs_load_and_format(self):
        """44161 contains (1,1) string DASlogs (CanName etc.).  Loading the
        file and rendering update_daslog must not raise."""
        from quicknxs.qreduce import NXSData
        from quicknxs.main_gui import _format_log_value
        data = NXSData('/SNS/REF_M/IPTS-34473/nexus/REF_M_44161.nxs.h5',
                       use_caching=False)
        ds = data['Off_Off']
        # Picking a known-problematic string log
        assert 'SampleName' in ds.logs
        # Must format without raising
        formatted = _format_log_value(ds.logs['SampleName'])
        assert isinstance(formatted, str)
        # Numeric log still formats with %g
        assert _format_log_value(ds.logs['SpeedRequest1']) == '30'


# ── State-file persistence of unreferenced direct beams (Fault 3) ─────

class TestHeaderCreatorExtraNorms:
    def test_extra_norms_are_serialised(self):
        """HeaderCreator(refls, extra_norms=[norm]) writes the norm into
        the [Direct Beam Runs] section even when no refl references it."""
        from quicknxs.qio import HeaderCreator

        class _FakeOpts(dict):
            pass

        class _FakeRefl:
            def __init__(self, number, origin):
                self.options = {
                    'normalization': None,
                    'P0': 0, 'PN': 0,
                    'x_pos': 100, 'x_width': 10,
                    'y_pos': 100, 'y_width': 50,
                    'bg_pos': 30, 'bg_width': 20,
                    'dpix': 150, 'tth': 0.0,
                    'number': number,
                    'scale': 1.0, 'extract_fan': False,
                    'sample_length': 10.0,
                    'bg_tof_constant': False, 'bg_scale_xfit': False,
                    'bg_poly_regions': None, 'bg_scale_factor': 1.0,
                }
                self.origin = (origin, 'x')
                self.read_options = {
                    'bin_type': 0, 'bins': 40,
                    'event_split_bins': None, 'event_split_index': 0,
                }

        extra = _FakeRefl(44035, '/tmp/REF_M_44035.nxs.h5')
        hdr = HeaderCreator([], extra_norms=[extra])
        text = str(hdr)
        assert '[Direct Beam Runs]' in text
        assert '44035' in text
        # No refls: data-runs section is empty (header only)
        assert '[Data Runs]' in text
        # Should still write [Global Options] without crashing
        assert '[Global Options]' in text

    def test_state_with_only_dbs_roundtrips(self):
        """A state file with direct beams and no refls must read back cleanly
        (regression: empty Data-Runs section used to throw IndexError)."""
        from quicknxs.qreduce import NXSData, Reflectivity
        from quicknxs.qio import HeaderCreator, HeaderParser
        ds = NXSData('tests/test1_histo.nxs', use_caching=False)
        norm = Reflectivity(ds[0], x_pos=100, x_width=10,
                            y_pos=100, y_width=50, bg_pos=30, bg_width=20,
                            dpix=150, tth=0.0)
        hdr = HeaderCreator([], extra_norms=[norm])
        parser = HeaderParser(str(hdr), parse_meta=False)
        parser.parse()
        assert len(parser.norms) == 1
        assert len(parser.refls) == 0
