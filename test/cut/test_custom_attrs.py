from math import isclose
from tempfile import NamedTemporaryFile

import numpy as np
import pytest

from lhotse import CutSet, LilcomHdf5Writer, MonoCut, NumpyHdf5Writer
from lhotse.cut import MixedCut, PaddingCut
from lhotse.serialization import deserialize_item
from lhotse.testing.dummies import dummy_cut, dummy_recording


@pytest.mark.parametrize("cut", [dummy_cut(1), dummy_cut(2).pad(300)])
def test_cut_nonexistent_attribute(cut):
    with pytest.raises(AttributeError):
        cut.nonexistent_attribute


def test_cut_load_array():
    """Check that a custom Array attribute is successfully recognized."""
    ivector = np.arange(20).astype(np.float32)
    with NamedTemporaryFile(suffix=".h5") as f, LilcomHdf5Writer(f.name) as writer:
        manifest = writer.store_array(key="utt1", value=ivector)
        cut = MonoCut(id="x", start=0, duration=5, channel=0)
        # Note: MonoCut doesn't normally have an "ivector" attribute,
        #       and a "load_ivector()" method.
        #       We are dynamically extending it.
        cut.ivector = manifest
        restored_ivector = cut.load_ivector()
        np.testing.assert_equal(ivector, restored_ivector)


def test_cut_load_array_truncate():
    """Check that loading a custom Array works after truncation."""
    ivector = np.arange(20).astype(np.float32)
    with NamedTemporaryFile(suffix=".h5") as f, LilcomHdf5Writer(f.name) as writer:
        cut = MonoCut(id="x", start=0, duration=5, channel=0)
        cut.ivector = writer.store_array(key="utt1", value=ivector)

        cut = cut.truncate(duration=3)

        restored_ivector = cut.load_ivector()
        np.testing.assert_equal(ivector, restored_ivector)


def test_cut_load_array_pad():
    """Check that loading a custom Array works after padding."""
    ivector = np.arange(20).astype(np.float32)
    with NamedTemporaryFile(suffix=".h5") as f, LilcomHdf5Writer(f.name) as writer:
        cut = MonoCut(
            id="x", start=0, duration=5, channel=0, recording=dummy_recording(1)
        )
        cut.ivector = writer.store_array(key="utt1", value=ivector)

        cut = cut.pad(duration=7.6)

        restored_ivector = cut.load_ivector()
        np.testing.assert_equal(ivector, restored_ivector)


def test_cut_custom_attr_serialization():
    """Check that a custom Array attribute is successfully serialized + deserialized."""
    ivector = np.arange(20).astype(np.float32)
    with NamedTemporaryFile(suffix=".h5") as f, LilcomHdf5Writer(f.name) as writer:
        cut = MonoCut(id="x", start=0, duration=5, channel=0)
        cut.ivector = writer.store_array(key="utt1", value=ivector)

        data = cut.to_dict()
        restored_cut = deserialize_item(data)
        assert cut == restored_cut

        restored_ivector = restored_cut.load_ivector()
        np.testing.assert_equal(ivector, restored_ivector)


def test_cut_custom_nonarray_attr_serialization():
    """Check that arbitrary custom fields work with Cuts upon (de)serialization."""
    cut = MonoCut(id="x", start=10, duration=8, channel=0, custom={"SNR": 7.3})

    data = cut.to_dict()
    restored_cut = deserialize_item(data)
    assert cut == restored_cut

    # Note: we extended cuts attributes by setting the "custom" field.
    assert restored_cut.SNR == 7.3


def test_cut_load_temporal_array():
    """Check that we can read a TemporalArray from a cut when their durations match."""
    alignment = np.random.randint(500, size=131)
    with NamedTemporaryFile(suffix=".h5") as f, NumpyHdf5Writer(f.name) as writer:
        manifest = writer.store_array(
            key="utt1", value=alignment, frame_shift=0.4, temporal_dim=0
        )
        expected_duration = 52.4  # 131 frames x 0.4s frame shift == 52.4s
        cut = MonoCut(id="x", start=0, duration=expected_duration, channel=0)
        # Note: MonoCut doesn't normally have an "alignment" attribute,
        #       and a "load_alignment()" method.
        #       We are dynamically extending it.
        cut.alignment = manifest
        restored_alignment = cut.load_alignment()
        np.testing.assert_equal(alignment, restored_alignment)


def test_cut_load_temporal_array_truncate():
    """Check the array loaded via TemporalArray is truncated along with the cut."""
    with NamedTemporaryFile(suffix=".h5") as f, NumpyHdf5Writer(f.name) as writer:
        expected_duration = 52.4  # 131 frames x 0.4s frame shift == 52.4s
        cut = MonoCut(id="x", start=0, duration=expected_duration, channel=0)

        alignment = np.random.randint(500, size=131)
        cut.alignment = writer.store_array(
            key="utt1", value=alignment, frame_shift=0.4, temporal_dim=0
        )
        cut_trunc = cut.truncate(duration=5.0)

        alignment_piece = cut_trunc.load_alignment()
        assert alignment_piece.shape == (13,)  # 5.0 / 0.4 == 12.5 ~= 13
        np.testing.assert_equal(alignment[:13], alignment_piece)


@pytest.mark.parametrize("pad_value", [-1, 0])
def test_cut_load_temporal_array_pad(pad_value):
    """Check the array loaded via TemporalArray is padded along with the cut."""
    with NamedTemporaryFile(suffix=".h5") as f, NumpyHdf5Writer(f.name) as writer:
        cut = MonoCut(
            id="x",
            start=0,
            duration=52.4,  # 131 frames x 0.4s frame shift == 52.4s
            channel=0,
            recording=dummy_recording(1),
        )

        alignment = np.random.randint(500, size=131)
        cut.alignment = writer.store_array(
            key="utt1", value=alignment, frame_shift=0.4, temporal_dim=0
        )
        cut_pad = cut.pad(duration=60.0, pad_value_dict={"alignment": pad_value})

        alignment_pad = cut_pad.load_alignment()
        assert alignment_pad.shape == (150,)  # 60.0 / 0.4 == 150
        np.testing.assert_equal(alignment_pad[:131], alignment)
        np.testing.assert_equal(alignment_pad[131:], pad_value)


def test_padding_issue_478():
    """
    https://github.com/lhotse-speech/lhotse/issues/478
    """
    with NamedTemporaryFile(suffix=".h5") as f, NumpyHdf5Writer(f.name) as writer:

        # Prepare data for cut 1.
        cut1 = MonoCut(
            "c1", start=0, duration=4.9, channel=0, recording=dummy_recording(1)
        )
        ali1 = np.random.randint(500, size=(121,))
        fs1 = cut1.duration / ali1.shape[0]
        cut1.label_alignment = writer.store_array(
            "c1", ali1, frame_shift=fs1, temporal_dim=0
        )

        # We expected frame shift to be 0.04, but it is actually larger than that!
        assert isclose(fs1, 0.04049586776859505)

        # Prepare data for cut 2.
        cut2 = MonoCut(
            "c2", start=0, duration=4.895, channel=0, recording=dummy_recording(2)
        )
        ali2 = np.random.randint(500, size=(121,))
        fs2 = cut2.duration / ali2.shape[0]
        cut2.label_alignment = writer.store_array(
            "c2", ali2, frame_shift=fs2, temporal_dim=0
        )

        # Note that this frame shift is actually different than in the other cut,
        # i.e. technically, each frame represents a slightly shorter chunk of
        # the recording in cut2 than in cut1. This is because the durations are
        # different, but the number of frames are the same.
        assert isclose(fs2, 0.04045454545454545)

        # Pad them. Cut 2 will have a PaddingCut.
        cuts = CutSet.from_cuts([cut1, cut2])
        cuts = cuts.pad()

        cut1_pad = cuts[0]
        assert isinstance(cut1_pad, MonoCut)
        cut2_pad = cuts[1]
        assert isinstance(cut2_pad, MixedCut)
        assert isinstance(cut2_pad.tracks[1].cut, PaddingCut)
        assert cut2_pad.tracks[1].cut.duration == 0.005

        arr1 = cuts[0].load_label_alignment()
        np.testing.assert_equal(arr1, ali1)

        arr2 = cuts[1].load_label_alignment()
        np.testing.assert_equal(arr2, ali2)
