#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 4K 修复补丁: 丢弃 DCI 4096x2160 视频格式, 强制 UHD 3840x2160 (LG 官方 Android 9 源码专用)
# 适用源码: gitlab.com/vostok/kernel_lge_msm @ LA.UM.7.4.r1-03500-8x98.0
# 用法: python3 patch_4k_a9.py [mdss_hdmi_edid.c 路径]
#   默认: drivers/video/fbdev/msm/mdss_hdmi_edid.c
# 已本地验证: 锚点 hdmi_edid_add_sink_y420_format(!sink) /
#   hdmi_edid_add_sink_video_format(HDMI_VFRMT_MAX) + 3 处 preferred_video_format sanitize
import sys
import re

p = sys.argv[1] if len(sys.argv) > 1 else 'drivers/video/fbdev/msm/mdss_hdmi_edid.c'

s = open(p, encoding='utf-8', errors='replace').read()
if 'hdmi_edid_is_dci_4k' in s:
    print('[patch_4k_a9] already patched, skip')
    sys.exit(0)

helper = '''static bool hdmi_edid_is_dci_4k(struct msm_hdmi_mode_timing_info *timing)
{
	return timing->active_h == 4096 && timing->active_v == 2160;
}

static u32 hdmi_edid_sanitize_preferred(u32 video_format)
{
	if (video_format >= HDMI_VFRMT_4096x2160p24_256_135 &&
		video_format <= HDMI_VFRMT_4096x2160p60_256_135)
		return HDMI_VFRMT_3840x2160p60_16_9;

	return video_format;
}
'''

dci_drop = '''\tif (hdmi_edid_is_dci_4k(&timing)) {
\t\tDEV_DBG("%s: dropping DCI 4K format %d [%s]\\n", __func__,
\t\t\tvideo_format, msm_hdmi_mode_2string(video_format));
\t\treturn;
\t}
'''


def insert_after_func(text, func_name, insert):
    idx = text.find(func_name)
    if idx < 0:
        raise SystemExit('func not found: ' + func_name)
    brace = text.find('{', idx)
    depth = 0
    pos = brace
    while pos < len(text):
        c = text[pos]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                break
        pos += 1
    return text[:pos + 1] + '\n' + insert + text[pos + 1:]


def insert_before(text, func_name, anchor, insert):
    idx = text.find(func_name)
    if idx < 0:
        raise SystemExit('func not found: ' + func_name)
    brace = text.find('{', idx)
    at = text.find(anchor, brace)
    if at < 0:
        raise SystemExit('anchor not found in ' + func_name + ': ' + anchor)
    return text[:at] + insert + text[at:]


# 1) helpers 插入到 hdmi_edid_find_hfvsdb 函数后
s = insert_after_func(s, 'static const u8 *hdmi_edid_find_hfvsdb', helper.rstrip('\n'))
print('[patch_4k_a9] helpers inserted')

# 2) DCI 丢弃块 (两个 add_sink 函数, 锚点按 LG A9 源码结构)
s = insert_before(s, 'hdmi_edid_add_sink_y420_format',
                  '\tif (!sink) {', dci_drop)
print('[patch_4k_a9] dci drop inserted in hdmi_edid_add_sink_y420_format')
s = insert_before(s, 'hdmi_edid_add_sink_video_format',
                  '\tif (video_format >= HDMI_VFRMT_MAX) {', dci_drop)
print('[patch_4k_a9] dci drop inserted in hdmi_edid_add_sink_video_format (A9 anchor)')

# 3) preferred_video_format 全部 sanitize 包装 (宽松匹配所有缩进)
s2 = re.sub(r'preferred_video_format\s*=\s*video_format;',
            'preferred_video_format =\n\t\t\t\t\t\thdmi_edid_sanitize_preferred(video_format);',
            s)
changed = s2 != s
s = s2
print('[patch_4k_a9] preferred sanitize wrapped:', changed, '| calls:',
      s.count('hdmi_edid_sanitize_preferred(video_format);'))

# 自检
assert s.count('{') == s.count('}'), 'brace imbalance'
assert s.count('hdmi_edid_is_dci_4k(struct msm_hdmi_mode_timing_info') == 1
n_call = s.count('hdmi_edid_sanitize_preferred(video_format);')
assert n_call >= 2, 'sanitize calls < 2'

open(p, 'w', encoding='utf-8', newline='').write(s)
print('[patch_4k_a9] OK: 4K patch applied (%d -> %d bytes)' % (
    len(s) - (len(helper) + 2 * len(dci_drop) + n_call * len(
        'hdmi_edid_sanitize_preferred(video_format);'
    ) - n_call * len('video_format;')), len(s)))
