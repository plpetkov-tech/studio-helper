import pytest
from studio_helper.video import fit as F

STORY = (1080, 1920)


def test_same_shape_fills_with_no_fill_and_no_offset():
    r = F.fit(*STORY, 1080, 1920)
    assert r.fill_fraction == 0 and r.offset_x == 0 and r.offset_y == 0
    assert r.concat_scale == pytest.approx(1)


def test_no_juice_box_means_cover_crop():
    r = F.fit(*STORY, 1600, 2560)  # LED Screen 1
    assert r.fill_fraction == 0
    assert r.scale == pytest.approx(max(1600 / 1080, 2560 / 1920))


def test_juice_box_keeps_everything_visible_and_zooms_in_as_far_as_it_can():
    juice = F.juice_box([0.25, 0.3, 0.5, 0.3], *STORY)  # middle band of the story
    r = F.fit(*STORY, 512, 3968, juice)  # Veliko Turnovo strip
    # the 540 px wide juice must fit in 512 px: scale = 512/540, fill appears above/below
    assert r.scale == pytest.approx(512 / 540)
    assert r.fill_fraction > 0
    vis_left = -r.left / r.scale
    assert vis_left <= juice.x and vis_left + 512 / r.scale >= juice.x + juice.w


def test_offsets_put_the_juice_centre_mid_screen_when_there_is_room():
    juice = F.juice_box([0.0, 0.0, 0.2, 0.2], *STORY)  # top-left corner of the master
    r = F.fit(*STORY, 1080, 1920, juice)
    # same shape: cover crop clamps, so the picture can't slide off-screen
    assert r.fill_fraction == 0 and r.left == 0 and r.top == 0


def test_story_ui_bands_keep_the_juice_out_from_under_instagrams_ui():
    juice = F.juice_box([0, 0, 1, 0.9], 1920, 1080)  # wide master, almost all of it matters
    r = F.fit(1920, 1080, 1080, 1920, juice, top=250, bottom=340)
    y0 = r.top + juice.y * r.scale
    y1 = r.top + (juice.y + juice.h) * r.scale
    assert y0 >= 250 - 1e-6 and y1 <= 1920 - 340 + 1e-6


def test_moving_juice_keeps_one_zoom():
    a = F.juice_box([0.4, 0.1, 0.3, 0.2], *STORY)
    b = F.juice_box([0.4, 0.6, 0.3, 0.2], *STORY)
    keyed = F.fit_keyed(*STORY, 1920, 1440, [(0.0, a), (6.0, b)])
    assert keyed[0][1].scale == keyed[1][1].scale
    assert keyed[0][1].offset_y != keyed[1][1].offset_y  # it follows the subject down


def test_concat_units_match_its_definition():
    # 1080x1920 on a 1920x1440 screen: scale 1 = fit = 1440/1920 = 0.75 px per px
    r = F.fit(*STORY, 1920, 1440)
    assert r.concat_scale == pytest.approx(r.scale / 0.75)


def test_panel_widths():
    assert F.panel_widths(1920, 3, 4) == [(1920 - 8) / 3] * 3


def test_repeat_panels_cover_each_column_and_stay_in_it():
    panels = F.repeat_panels(1080, 1920, 1920, 1440, 3, 4)
    pw = (1920 - 8) / 3
    for i, p in enumerate(panels):
        centre_px = 960 + p.offset_x * 1920
        assert i * (pw + 4) <= centre_px <= i * (pw + 4) + pw
        assert p.fill_fraction == 0  # a 9:16 master covers a 637x1440 column
        assert 0 <= p.crop["left"] < 1 - p.crop["right"] <= 1
