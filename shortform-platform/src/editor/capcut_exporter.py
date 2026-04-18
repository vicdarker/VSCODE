"""
CapCut PC 프로젝트 파일 생성기.
실제 CapCut JSON 구조를 사용해 바로 열 수 있는 프로젝트를 생성합니다.
"""

import json
import os
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from src.selector.claude_selector import ShortsScript, SelectedClip

# 뉴스 숏츠 레이아웃: 상단 630px 검정 + 중앙 810px 영상(4:3) + 하단 480px 검정
_NEWS_TOP_H = 630
_NEWS_VID_H = 810


def _letterbox_news(src_path: str, dst_path: str) -> str:
    """영상/사진(1080x810)을 상단+하단 검정 레터박스 포함 1080x1920으로 합성"""
    # 입력이 어떤 크기든 1080x810 중앙 영역에 cover 방식으로 맞추고 black 패딩
    vf = (
        f"scale=1080:{_NEWS_VID_H}:force_original_aspect_ratio=increase,"
        f"crop=1080:{_NEWS_VID_H},"
        f"pad=1080:1920:0:{_NEWS_TOP_H}:black,setsar=1"
    )
    subprocess.run([
        "ffmpeg", "-y", "-i", src_path,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p", "-an",
        dst_path,
    ], capture_output=True, check=True)
    return dst_path


def _uid() -> str:
    return str(uuid.uuid4()).upper()


def export_script_to_capcut(
    video_path: str,
    script: ShortsScript,
    output_dir: str = "output/capcut",
) -> str:
    abs_video = _host_path(os.path.abspath(video_path))
    stem = Path(video_path).stem
    project_name = stem + "_shorts"

    # CapCut Drafts에 직접 저장 (마운트된 경우)
    drafts_root = os.environ.get("CAPCUT_DRAFTS_PATH", "")
    if drafts_root and Path(drafts_root).exists():
        project_dir = Path(drafts_root) / project_name
    else:
        project_dir = Path(output_dir) / project_name

    project_dir.mkdir(parents=True, exist_ok=True)

    video_mat_id = _uid()
    total_dur_us = sum(int((s.end - s.start) * 1_000_000) for s in script.segments)

    content = _build_content(abs_video, video_mat_id, total_dur_us, script)
    meta = _build_meta(project_name, project_dir, abs_video, video_mat_id, script.title)

    (project_dir / "draft_content.json").write_text(
        json.dumps(content, ensure_ascii=False), encoding="utf-8"
    )
    (project_dir / "draft_meta_info.json").write_text(
        json.dumps(meta, ensure_ascii=False), encoding="utf-8"
    )
    (project_dir / "plan.txt").write_text(
        _build_plan_txt(script), encoding="utf-8"
    )

    _update_root_meta(project_dir, project_name, meta["id"], script.title)

    # output/capcut 에도 백업
    backup = Path(output_dir) / project_name
    if str(project_dir) != str(backup):
        if backup.exists():
            shutil.rmtree(backup)
        shutil.copytree(project_dir, backup)

    print(f"  CapCut 프로젝트 생성 완료: {project_dir}")
    return str(project_dir)


# ── 핵심 JSON 빌더 ────────────────────────────────────────────────────────────

def _build_content(abs_video: str, video_mat_id: str, total_dur_us: int, script: ShortsScript) -> dict:
    video_material = _make_video_material(video_mat_id, abs_video, total_dur_us)

    # 오디오 페이드 재료 생성 (구간마다 fade in/out 300ms)
    audio_fade_mats = []
    audio_fade_ids = []
    for _ in script.segments:
        fade_id = _uid()
        audio_fade_ids.append(fade_id)
        audio_fade_mats.append({
            "id": fade_id,
            "type": "audio_fade",
            "fade_type": 0,
            "fade_in_duration":  300_000,   # 0.3초
            "fade_out_duration": 300_000,
        })

    # 비디오 트랙 세그먼트
    video_segments = []
    timeline_pos = 0
    for idx, seg in enumerate(script.segments):
        src_start = int(seg.start * 1_000_000)
        src_dur   = int((seg.end - seg.start) * 1_000_000)
        video_segments.append(_make_video_segment(
            seg_id=_uid(),
            mat_id=video_mat_id,
            src_start=src_start,
            src_dur=src_dur,
            tgt_start=timeline_pos,
            audio_fade_id=audio_fade_ids[idx],
        ))
        timeline_pos += src_dur

    tracks = [{
        "attribute": 0,
        "flag": 0,
        "id": _uid(),
        "is_default_name": True,
        "name": "",
        "segments": video_segments,
        "type": "video",
    }]

    return {
        "canvas_config": {"background": None, "height": 1920, "ratio": "9:16", "width": 1080},
        "color_space": -1,
        "config": _default_config(),
        "cover": None,
        "create_time": 0,
        "draft_type": "video",
        "duration": total_dur_us,
        "extra_info": None,
        "fps": 30.0,
        "free_render_index_mode_on": False,
        "function_assistant_info": _default_function_assistant(),
        "group_container": None,
        "id": _uid(),
        "is_drop_frame_timecode": False,
        "keyframe_graph_list": [],
        "keyframes": {"adjusts": [], "audios": [], "effects": [], "filters": [], "handwrites": [], "stickers": [], "texts": [], "videos": []},
        "last_modified_platform": _platform_info(),
        "lyrics_effects": [],
        "materials": _build_materials(video_material, audio_fade_mats),
        "mutable_config": None,
        "name": script.title or "",
        "new_version": "167.0.0",
        "path": "",
        "platform": _platform_info(),
        "relationships": [],
        "render_index_track_mode_on": True,
        "retouch_cover": None,
        "smart_ads_info": {"draft_url": "", "page_from": "", "routine": ""},
        "source": "default",
        "static_cover_image_path": "",
        "time_marks": None,
        "tracks": tracks,
        "uneven_animation_template_info": {"composition": "", "content": "", "order": "", "sub_template_info_list": []},
        "update_time": 0,
        "version": 360000,
    }


def _make_video_material(mat_id: str, path: str, duration_us: int) -> dict:
    return {
        "id": mat_id,
        "unique_id": "",
        "type": "video",
        "duration": duration_us,
        "path": path,
        "media_path": "",
        "local_id": "",
        "has_audio": True,
        "reverse_path": "",
        "intensifies_path": "",
        "reverse_intensifies_path": "",
        "intensifies_audio_path": "",
        "cartoon_path": "",
        "width": 1920,
        "height": 1080,
        "category_id": "",
        "category_name": "local",
        "material_id": "",
        "material_name": Path(path).name,
        "material_url": "",
        "crop": {"upper_left_x": 0.0, "upper_left_y": 0.0, "upper_right_x": 1.0, "upper_right_y": 0.0, "lower_left_x": 0.0, "lower_left_y": 1.0, "lower_right_x": 1.0, "lower_right_y": 1.0},
        "crop_ratio": "free",
        "audio_fade": None,
        "crop_scale": 1.0,
        "extra_type_option": 0,
        "stable": {"stable_level": 0, "matrix_path": "", "time_range": {"start": 0, "duration": 0}},
        "matting": {"flag": 0, "path": "", "interactiveTime": [], "has_use_quick_brush": False, "strokes": [], "has_use_quick_eraser": False, "expansion": 0, "feather": 0, "reverse": False, "custom_matting_id": "", "enable_matting_stroke": False},
        "source": 0,
        "source_platform": 0,
        "formula_id": "",
        "check_flag": 62978047,
        "video_algorithm": {
            "algorithms": [], "time_range": None, "path": "", "gameplay_configs": [],
            "ai_in_painting_config": [], "complement_frame_config": None,
            "motion_blur_config": None, "deflicker": None, "noise_reduction": None,
            "quality_enhance": None, "super_resolution": None, "ai_background_configs": [],
            "smart_complement_frame": None, "aigc_generate": None, "aigc_generate_list": [],
            "mouth_shape_driver": None, "ai_expression_driven": None, "ai_motion_driven": None,
            "image_interpretation": None,
            "story_video_modify_video_config": {"task_id": "", "is_overwrite_last_video": False, "tracker_task_id": ""},
            "skip_algorithm_index": [],
        },
        "is_unified_beauty_mode": False,
        "object_locked": None,
        "smart_motion": None,
        "multi_camera_info": None,
        "freeze": None,
        "picture_from": "none",
        "picture_set_category_id": "",
        "picture_set_category_name": "",
        "team_id": "",
        "local_material_id": str(uuid.uuid4()),
        "origin_material_id": "",
        "request_id": "",
        "has_sound_separated": False,
        "is_text_edit_overdub": False,
        "is_ai_generate_content": False,
        "aigc_type": "none",
        "is_copyright": False,
        "aigc_history_id": "",
        "aigc_item_id": "",
        "local_material_from": "",
        "smart_match_info": None,
        "beauty_face_preset_infos": [],
        "beauty_body_preset_id": "",
        "beauty_face_auto_preset": {"preset_id": "", "name": "", "rate_map": "", "scene": ""},
        "beauty_face_auto_preset_infos": [],
        "beauty_body_auto_preset": None,
        "live_photo_timestamp": -1,
        "live_photo_cover_path": "",
        "content_feature_info": None,
        "corner_pin": None,
        "surface_trackings": [],
        "video_mask_stroke": {"resource_id": "", "path": "", "type": "", "color": "", "size": 0.0, "alpha": 0.0, "distance": 0.0, "texture": 0.0, "horizontal_shift": 0.0, "vertical_shift": 0.0},
        "video_mask_shadow": {"resource_id": "", "path": "", "color": "", "alpha": 0.0, "blur": 0.0, "distance": 0.0, "angle": 0.0},
    }


def _make_video_segment(seg_id, mat_id, src_start, src_dur, tgt_start, audio_fade_id=None) -> dict:
    return {
        "id": seg_id,
        "source_timerange": {"start": src_start, "duration": src_dur},
        "target_timerange": {"start": tgt_start, "duration": src_dur},
        "render_timerange": {"start": 0, "duration": 0},
        "desc": "",
        "state": 0,
        "speed": 1.0,
        "is_loop": False,
        "is_tone_modify": False,
        "reverse": False,
        "intensifies_audio": False,
        "cartoon": False,
        "volume": 1.0,
        "last_nonzero_volume": 1.0,
        "clip": {"scale": {"x": 1.0, "y": 1.0}, "rotation": 0.0, "transform": {"x": 0.0, "y": 0.0}, "flip": {"vertical": False, "horizontal": False}, "alpha": 1.0},
        "uniform_scale": {"on": True, "value": 1.0},
        "material_id": mat_id,
        "extra_material_refs": [audio_fade_id] if audio_fade_id else [],
        "render_index": 0,
        "keyframe_refs": [],
        "enable_lut": True,
        "enable_adjust": True,
        "enable_hsl": True,
        "visible": True,
        "group_id": "",
        "enable_color_curves": True,
        "enable_hsl_curves": True,
        "track_render_index": 0,
        "hdr_settings": {"mode": 1, "intensity": 1.0, "nits": 1000},
        "enable_color_wheels": True,
        "track_attribute": 1,
        "is_placeholder": False,
        "template_id": "",
        "enable_smart_color_adjust": False,
        "template_scene": "default",
        "common_keyframes": [],
        "caption_info": None,
        "responsive_layout": {"enable": False, "target_follow": "", "size_layout": 0, "horizontal_pos_layout": 0, "vertical_pos_layout": 0},
        "enable_color_match_adjust": False,
        "enable_color_correct_adjust": False,
        "enable_adjust_mask": True,
        "raw_segment_id": "",
        "lyric_keyframes": None,
        "enable_video_mask": True,
        "digital_human_template_group_id": "",
        "color_correct_alg_result": "",
        "source": "segmentsourcenormal",
        "enable_mask_stroke": False,
        "enable_mask_shadow": False,
        "enable_color_adjust_pro": False,
    }


def _make_news_title_material(mat_id: str, text: str) -> dict:
    """뉴스 숏츠 상단 타이틀 — 검정 배경 위 굵은 흰 글씨 (삼프로tv 스타일)"""
    mat = _make_text_material(mat_id, text)
    mat.update({
        "font_size": 7.5,
        "text_size": 11,
        "bold_width": 0.6,
        "alignment": 1,
        "line_max_width": 0.80,
        "text_color": "#FFFFFFFF",
        "has_shadow": False,
        "border_width": 0.0,
        "line_spacing": 0.1,
    })
    return mat


def _make_news_source_material(mat_id: str, text: str = "출처:삼프로tv") -> dict:
    """상단 출처 표기 — 아주 작은 흰 글씨"""
    mat = _make_text_material(mat_id, text)
    mat.update({
        "font_size": 3.5,
        "text_size": 5,
        "alignment": 1,
        "line_max_width": 0.4,
        "text_color": "#FFFFFFFF",
        "has_shadow": False,
        "border_width": 0.0,
    })
    return mat


def _make_news_caption_material(mat_id: str, text: str) -> dict:
    """뉴스 숏츠 하단 자막 — 노란색 굵은 글씨"""
    mat = _make_text_material(mat_id, text)
    mat.update({
        "font_size": 5.5,
        "text_size": 9,
        "bold_width": 0.5,
        "alignment": 1,
        "line_max_width": 0.88,
        "text_color": "#FFF000",
        "text_alpha": 1.0,
        "use_effect_default_color": False,
        "border_width": 0.08,
        "border_color": "#000000",
        "shadow_distance": 4.0,
        "shadow_alpha": 0.9,
    })
    return mat


def _make_positioned_text_segment(seg_id, mat_id, src_dur, tgt_start, y_pos: float) -> dict:
    seg = _make_text_segment(seg_id, mat_id, src_dur, tgt_start)
    seg["clip"]["transform"]["y"] = y_pos
    return seg


def _make_text_material(mat_id: str, text: str) -> dict:
    return {
        "add_type": 0, "alignment": 1, "background_alpha": 1.0, "background_color": "",
        "background_fill": "", "background_height": 0.14, "background_horizontal_offset": 0.0,
        "background_round_radius": 0.0, "background_style": 0, "background_vertical_offset": 0.0,
        "background_width": 0.14, "base_content": "", "bold_width": 0.0,
        "border_alpha": 1.0, "border_color": "#000000", "border_mode": 0, "border_width": 0.08,
        "caption_template_info": {"category_id": "", "category_name": "", "effect_id": "",
                                   "is_new": False, "path": "", "request_id": "",
                                   "resource_id": "", "resource_name": "", "source_platform": 0,
                                   "third_resource_id": ""},
        "check_flag": 7, "combo_info": {"text_templates": []}, "content": text,
        "cutoff_postfix": "", "fixed_height": -1.0, "fixed_width": -1.0,
        "font_category_id": "", "font_category_name": "", "font_id": "", "font_name": "",
        "font_path": "", "font_resource_id": "", "font_size": 11.0, "font_source_platform": 0,
        "font_team_id": "", "font_third_resource_id": "", "font_title": "none", "font_url": "",
        "fonts": [], "force_apply_line_max_width": False, "global_alpha": 1.0, "group_id": "",
        "has_shadow": True, "id": mat_id, "initial_scale": 1.0, "inner_padding": -1.0,
        "is_batch_replace": False, "is_lyric_effect": False, "is_rich_text": False,
        "is_words_linear": False, "italic_degree": 0, "ktv_color": "#FF0000FF",
        "language": "", "layer_weight": 1, "letter_spacing": 0.0, "line_feed": 1,
        "line_max_width": 0.82, "line_spacing": 0.0, "lyric_group_id": "",
        "lyrics_template": {"category_id": "", "category_name": "", "effect_id": "",
                            "panel": "", "path": "", "request_id": "", "resource_id": "",
                            "resource_name": ""},
        "multi_language_current": "none", "name": "", "offset_on_path": 0.0,
        "oneline_cutoff": False, "operation_type": 0, "original_size": [],
        "preset_category": "", "preset_category_id": "", "preset_has_set_alignment": False,
        "preset_id": "", "preset_index": 0, "preset_name": "", "punc_model": "",
        "recognize_model": "", "recognize_task_id": "", "recognize_text": "",
        "recognize_type": 0, "relevance_segment": [], "shape_clip_x": False,
        "shape_clip_y": False, "single_char_bg_alpha": 1.0, "single_char_bg_color": "",
        "single_char_bg_enable": False, "single_char_bg_height": 0.0,
        "single_char_bg_horizontal_offset": 0.0, "single_char_bg_round_radius": 0.3,
        "single_char_bg_vertical_offset": 0.0, "single_char_bg_width": 0.0,
        "source_from": "", "ssml_content": "", "style_name": "", "sub_template_id": -1,
        "sub_type": 0, "subtitle_keywords": None, "subtitle_keywords_config": None,
        "subtitle_template_original_fontsize": 0.0, "text_alpha": 1.0,
        "text_color": "#FFFFFFFF", "text_curve": None, "text_exceeds_path_process_type": 0,
        "text_loop_on_path": False, "text_preset_resource_id": "", "text_size": 18,
        "text_to_audio_ids": [], "text_typesetting_path_index": 0,
        "text_typesetting_paths": None, "text_typesetting_paths_file": "",
        "translate_original_text": "", "tts_auto_update": False, "type": "text",
        "typesetting": 0, "underline": False, "underline_offset": 0.22, "underline_width": 0.05,
        "use_effect_default_color": True,
        "shadow_alpha": 0.8, "shadow_angle": -45.0, "shadow_color": "#000000",
        "shadow_distance": 8.0, "shadow_point": {"x": 1.0182337649086284, "y": -1.0182337649086284},
        "shadow_smoothing": 0.99, "shadow_thickness_projection_angle": 0.0,
        "shadow_thickness_projection_distance": 0.0, "shadow_thickness_projection_enable": False,
        "enable_path_typesetting": False,
        "words": {"end_time": [], "start_time": [], "text": []},
        "current_words": {"end_time": [], "start_time": [], "text": []},
    }


def _make_text_segment(seg_id: str, mat_id: str, src_dur: int, tgt_start: int) -> dict:
    return {
        "id": seg_id,
        "source_timerange": None,
        "target_timerange": {"start": tgt_start, "duration": src_dur},
        "render_timerange": {"start": 0, "duration": 0},
        "desc": "",
        "state": 0,
        "speed": 1.0,
        "is_loop": False,
        "is_tone_modify": False,
        "reverse": False,
        "intensifies_audio": False,
        "cartoon": False,
        "volume": 1.0,
        "last_nonzero_volume": 1.0,
        "clip": {"scale": {"x": 1.0, "y": 1.0}, "rotation": 0.0,
                 "transform": {"x": 0.0, "y": -0.25},
                 "flip": {"vertical": False, "horizontal": False}, "alpha": 1.0},
        "uniform_scale": {"on": True, "value": 1.0},
        "material_id": mat_id,
        "extra_material_refs": [],
        "render_index": 14000,
        "keyframe_refs": [],
        "enable_lut": False,
        "enable_adjust": False,
        "enable_hsl": False,
        "visible": True,
        "group_id": "",
        "enable_color_curves": True,
        "enable_hsl_curves": True,
        "track_render_index": 2,
        "hdr_settings": None,
        "enable_color_wheels": True,
        "track_attribute": 0,
        "is_placeholder": False,
        "template_id": "",
        "enable_smart_color_adjust": False,
        "template_scene": "default",
        "common_keyframes": [],
        "caption_info": None,
        "responsive_layout": {"enable": False, "target_follow": "", "size_layout": 0,
                              "horizontal_pos_layout": 0, "vertical_pos_layout": 0},
        "enable_color_match_adjust": False,
        "enable_color_correct_adjust": False,
        "enable_adjust_mask": True,
        "raw_segment_id": "",
        "lyric_keyframes": None,
        "enable_video_mask": True,
        "digital_human_template_group_id": "",
        "color_correct_alg_result": "",
        "source": "segmentsourcenormal",
        "enable_mask_stroke": False,
        "enable_mask_shadow": False,
        "enable_color_adjust_pro": False,
    }


def _build_materials(video_material: dict, audio_fade_mats: list = None) -> dict:
    return _build_materials_multi([video_material], audio_fade_mats)


def _build_materials_multi(video_materials: list, audio_fade_mats: list = None,
                           text_materials: list = None) -> dict:
    return {
        "ai_translates": [], "audio_balances": [], "audio_effects": [], "audio_fades": audio_fade_mats or [],
        "audio_pannings": [], "audio_pitch_shifts": [], "audio_track_indexes": [],
        "audios": [], "beats": [], "canvases": [], "chromas": [], "color_curves": [],
        "common_mask": [], "digital_human_model_dressing": [], "digital_humans": [],
        "drafts": [], "effects": [], "flowers": [], "green_screens": [], "handwrites": [],
        "hsl": [], "hsl_curves": [], "images": [], "log_color_wheels": [], "loudnesses": [],
        "manual_beautys": [], "manual_deformations": [], "material_animations": [],
        "material_colors": [], "multi_language_refs": [], "placeholder_infos": [],
        "placeholders": [], "plugin_effects": [], "primary_color_wheels": [],
        "realtime_denoises": [], "shapes": [], "smart_crops": [], "smart_relights": [],
        "sound_channel_mappings": [], "speeds": [], "stickers": [], "tail_leaders": [],
        "text_templates": [], "texts": text_materials or [], "time_marks": [], "transitions": [],
        "video_effects": [], "video_radius": [], "video_shadows": [], "video_strokes": [],
        "video_trackings": [], "videos": video_materials, "vocal_beautifys": [],
        "vocal_separations": [],
    }


def _build_meta(project_name, project_dir, abs_video, video_mat_id, title) -> dict:
    now_ms = int(time.time() * 1000)
    draft_id = _uid()
    host_dir = str(project_dir).replace("/capcut_drafts", "C:/Users/vicmy/AppData/Local/CapCut Drafts").replace("/", "\\")
    return {
        "id": draft_id,
        "draft_name": title or project_name,
        "draft_root_path": "C:\\Users\\vicmy\\AppData\\Local\\CapCut Drafts",
        "draft_fold_path": host_dir,
        "draft_json_file": host_dir + "\\draft_content.json",
        "draft_cover": host_dir + "\\draft_cover.jpg",
        "draft_new_version": "167.0.0",
        "draft_timeline_materials_size": 0,
        "draft_type": "",
        "draft_materials": [{"value": [{"file_Path": abs_video, "file_id": video_mat_id, "file_name": Path(abs_video).name}]}],
        "tm_draft_create": now_ms,
        "tm_draft_modified": now_ms,
        "tm_draft_removed": 0,
        "tm_duration": 0,
        "cloud_draft_cover": False,
        "cloud_draft_sync": False,
        "draft_cloud_last_action_download": False,
        "draft_cloud_purchase_info": "",
        "draft_cloud_template_id": "",
        "draft_cloud_tutorial_info": "",
        "draft_cloud_videocut_purchase_info": "",
        "draft_is_ai_shorts": False,
        "draft_is_cloud_temp_draft": False,
        "draft_is_invisible": False,
        "draft_is_web_article_video": False,
        "draft_web_article_video_enter_from": "",
        "streaming_edit_draft_ready": True,
        "tm_draft_cloud_completed": "",
        "tm_draft_cloud_entry_id": 0,
        "tm_draft_cloud_modified": 0,
        "tm_draft_cloud_parent_entry_id": 0,
        "tm_draft_cloud_space_id": 0,
        "tm_draft_cloud_user_id": 0,
    }


def _update_root_meta(project_dir: Path, project_name: str, draft_id: str, title: str):
    meta_root = os.environ.get("CAPCUT_META_PATH", "")
    if not meta_root:
        return
    root_meta_path = Path(meta_root) / "root_meta_info.json"
    if not root_meta_path.exists():
        return

    try:
        with open(root_meta_path, encoding="utf-8") as f:
            data = json.load(f)

        host_dir = "C:\\Users\\vicmy\\AppData\\Local\\CapCut Drafts\\" + project_name
        now_ms = int(time.time() * 1000)

        # 기존 동일 이름 항목 제거
        data["all_draft_store"] = [
            d for d in data["all_draft_store"]
            if d.get("draft_name") != (title or project_name)
            and d.get("draft_fold_path") != host_dir
        ]

        data["all_draft_store"].insert(0, {
            "cloud_draft_cover": False,
            "cloud_draft_sync": False,
            "draft_cloud_last_action_download": False,
            "draft_cloud_purchase_info": "",
            "draft_cloud_template_id": "",
            "draft_cloud_tutorial_info": "",
            "draft_cloud_videocut_purchase_info": "",
            "draft_cover": host_dir + "\\draft_cover.jpg",
            "draft_fold_path": host_dir,
            "draft_id": draft_id,
            "draft_is_ai_shorts": False,
            "draft_is_cloud_temp_draft": False,
            "draft_is_invisible": False,
            "draft_is_web_article_video": False,
            "draft_json_file": host_dir + "\\draft_content.json",
            "draft_name": title or project_name,
            "draft_new_version": "167.0.0",
            "draft_root_path": "C:\\Users\\vicmy\\AppData\\Local\\CapCut Drafts",
            "draft_timeline_materials_size": 0,
            "draft_type": "",
            "draft_web_article_video_enter_from": "",
            "streaming_edit_draft_ready": True,
            "tm_draft_cloud_completed": "",
            "tm_draft_cloud_entry_id": 0,
            "tm_draft_cloud_modified": 0,
            "tm_draft_cloud_parent_entry_id": 0,
            "tm_draft_cloud_space_id": 0,
            "tm_draft_cloud_user_id": 0,
            "tm_draft_create": now_ms,
            "tm_draft_modified": now_ms,
            "tm_draft_removed": 0,
            "tm_duration": 0,
        })

        with open(root_meta_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

        print("  root_meta_info.json 업데이트 완료")
    except Exception as e:
        print(f"  root_meta_info.json 업데이트 실패 (무시): {e}")


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def _host_path(container_path: str) -> str:
    host_base = os.environ.get("HOST_PROJECT_PATH", "")
    if host_base and container_path.startswith("/app/"):
        p = (host_base + "/" + container_path[5:]).replace("\\", "/")
    else:
        p = container_path.replace("\\", "/")
    # 드라이브 레터 대문자화 (C:/ 형식)
    if len(p) >= 2 and p[1] == ":" and p[0].islower():
        p = p[0].upper() + p[1:]
    return p


def _build_plan_txt(script: ShortsScript) -> str:
    lines = [
        f"제목: {script.title}",
        f"설명: {script.description}",
        f"해시태그: {' '.join(script.hashtags)}",
        "",
        "── 구성 ──",
    ]
    for i, seg in enumerate(script.segments, 1):
        dur = seg.end - seg.start
        lines.append(f"[{i}] {seg.role.upper()} | {seg.start:.1f}s~{seg.end:.1f}s ({dur:.1f}s)")
        if seg.text_overlay:
            lines.append(f"     오버레이: {seg.text_overlay}")
        lines.append(f"     자막: {seg.caption}")
    return "\n".join(lines)


def _default_config() -> dict:
    return {
        "adjust_max_index": 1, "attachment_info": [], "combination_max_index": 1,
        "export_range": None, "extract_audio_last_index": 1, "lyrics_recognition_id": "",
        "lyrics_sync": True, "lyrics_taskinfo": [], "maintrack_adsorb": True,
        "material_save_mode": 0, "multi_language_current": "none", "multi_language_list": [],
        "multi_language_main": "none", "multi_language_mode": "none",
        "original_sound_last_index": 1, "record_audio_last_index": 1,
        "sticker_max_index": 1, "subtitle_keywords_config": None,
        "subtitle_recognition_id": "", "subtitle_sync": True, "subtitle_taskinfo": [],
        "system_font_list": [], "use_float_render": False, "video_mute": False,
        "voice_change_sync": False, "zoom_info_params": None,
    }


def _default_function_assistant() -> dict:
    return {
        "audio_noise_segid_list": [], "auto_adjust": False, "auto_adjust_fixed": False,
        "auto_adjust_fixed_value": 50.0, "auto_adjust_segid_list": [], "auto_caption": False,
        "auto_caption_segid_list": [], "auto_caption_template_id": "", "caption_opt": False,
        "caption_opt_segid_list": [], "color_correction": False, "color_correction_fixed": False,
        "color_correction_fixed_value": 50.0, "color_correction_segid_list": [],
        "deflicker_segid_list": [], "enhance_quality": False, "enhance_quality_fixed": False,
        "enhance_quality_segid_list": [], "enhance_voice_segid_list": [], "enhande_voice": False,
        "enhande_voice_fixed": False, "eye_correction": False, "eye_correction_segid_list": [],
        "fixed_rec_applied": False, "fps": {"den": 1, "num": 0}, "normalize_loudness": False,
        "normalize_loudness_audio_denoise_segid_list": [], "normalize_loudness_fixed": False,
        "normalize_loudness_segid_list": [], "retouch": False, "retouch_fixed": False,
        "retouch_segid_list": [], "smart_rec_applied": False, "smart_segid_list": [],
        "smooth_slow_motion": False, "smooth_slow_motion_fixed": False,
        "video_noise_segid_list": [],
    }


def _platform_info() -> dict:
    return {
        "app_id": 359289, "app_source": "cc", "app_version": "8.5.0",
        "device_id": "c4ca4238a0b923820dcc509a6f75849b",
        "hard_disk_id": "767dfc323f83f8bfa32de4701cdea603",
        "mac_address": "3034e6270b2d7e4488f86e0b81e495c0",
        "os": "windows", "os_version": "10.0.26200",
    }


# ── 뉴스 숏츠 파이프라인 ────────────────────────────────────────────────────────

def export_news_to_capcut(news_script, output_dir: str = "output/capcut") -> str:
    """NewsScript → 각 세그먼트별 미디어를 가진 CapCut 프로젝트"""
    project_name = re.sub(r"[^\w]", "_", news_script.title[:30]) or "news_shorts"

    drafts_root = os.environ.get("CAPCUT_DRAFTS_PATH", "")
    if drafts_root and Path(drafts_root).exists():
        project_dir = Path(drafts_root) / project_name
    else:
        project_dir = Path(output_dir) / project_name
    project_dir.mkdir(parents=True, exist_ok=True)

    # 세그먼트별 비디오 재료 생성 (삼프로tv 스타일 레터박스 합성)
    video_materials, mat_ids = [], []
    for seg in news_script.segments:
        mat_id = _uid()
        mat_ids.append(mat_id)
        dur_us = int(seg.duration * 1_000_000)
        src = os.path.abspath(seg.media_path)
        lb = str(Path(src).with_name(Path(src).stem + "_lb.mp4"))
        try:
            _letterbox_news(src, lb)
            final_src = lb
        except Exception as e:
            print(f"  레터박스 실패 ({seg.media_path}): {e}")
            final_src = src
        abs_path = _host_path(final_src)
        video_materials.append(_make_video_material(mat_id, abs_path, dur_us))

    # 오디오 페이드
    audio_fade_mats, audio_fade_ids = [], []
    for _ in news_script.segments:
        fade_id = _uid()
        audio_fade_ids.append(fade_id)
        audio_fade_mats.append({
            "id": fade_id, "type": "audio_fade", "fade_type": 0,
            "fade_in_duration": 300_000, "fade_out_duration": 300_000,
        })

    # 타임라인 세그먼트 + 텍스트 재료 (타이틀/자막 분리)
    video_segments = []
    title_materials, title_segments = [], []
    caption_materials, caption_segments = [], []
    timeline_pos = 0
    for idx, seg in enumerate(news_script.segments):
        dur_us = int(seg.duration * 1_000_000)
        video_segments.append(_make_video_segment(
            seg_id=_uid(), mat_id=mat_ids[idx],
            src_start=0, src_dur=dur_us, tgt_start=timeline_pos,
            audio_fade_id=audio_fade_ids[idx],
        ))
        # 상단 타이틀 (text_content) — 검정 영역 중앙 (4:3 레이아웃 기준)
        if seg.text_content:
            t_id = _uid()
            title_materials.append(_make_news_title_material(t_id, seg.text_content))
            title_segments.append(_make_positioned_text_segment(
                _uid(), t_id, dur_us, timeline_pos, y_pos=0.67,
            ))
        # 하단 자막 (caption) — 검정 영역 (4:3 레이아웃 기준)
        if seg.caption:
            c_id = _uid()
            caption_materials.append(_make_news_caption_material(c_id, seg.caption))
            caption_segments.append(_make_positioned_text_segment(
                _uid(), c_id, dur_us, timeline_pos, y_pos=-0.75,
            ))
        timeline_pos += dur_us

    total_dur_us = timeline_pos
    all_text_materials = title_materials + caption_materials
    tracks = [{"attribute": 0, "flag": 0, "id": _uid(), "is_default_name": True,
                "name": "", "segments": video_segments, "type": "video"}]
    if title_segments:
        tracks.append({"attribute": 0, "flag": 0, "id": _uid(), "is_default_name": True,
                        "name": "타이틀", "segments": title_segments, "type": "text"})
    if caption_segments:
        tracks.append({"attribute": 0, "flag": 0, "id": _uid(), "is_default_name": True,
                        "name": "자막", "segments": caption_segments, "type": "text"})

    content = {
        "canvas_config": {"background": None, "height": 1920, "ratio": "9:16", "width": 1080},
        "color_space": -1, "config": _default_config(), "cover": None, "create_time": 0,
        "draft_type": "video", "duration": total_dur_us, "extra_info": None, "fps": 30.0,
        "free_render_index_mode_on": False, "function_assistant_info": _default_function_assistant(),
        "group_container": None, "id": _uid(), "is_drop_frame_timecode": False,
        "keyframe_graph_list": [],
        "keyframes": {"adjusts": [], "audios": [], "effects": [], "filters": [],
                      "handwrites": [], "stickers": [], "texts": [], "videos": []},
        "last_modified_platform": _platform_info(), "lyrics_effects": [],
        "materials": _build_materials_multi(video_materials, audio_fade_mats, all_text_materials),
        "mutable_config": None, "name": news_script.title or "", "new_version": "167.0.0",
        "path": "", "platform": _platform_info(), "relationships": [],
        "render_index_track_mode_on": True, "retouch_cover": None,
        "smart_ads_info": {"draft_url": "", "page_from": "", "routine": ""},
        "source": "default", "static_cover_image_path": "", "time_marks": None,
        "tracks": tracks,
        "uneven_animation_template_info": {"composition": "", "content": "", "order": "",
                                           "sub_template_info_list": []},
        "update_time": 0, "version": 360000,
    }

    draft_id = _uid()
    first_path = video_materials[0]["path"] if video_materials else ""
    first_mat_id = mat_ids[0] if mat_ids else ""
    meta = _build_meta(project_name, project_dir, first_path, first_mat_id, news_script.title)
    meta["id"] = draft_id

    (project_dir / "draft_content.json").write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
    (project_dir / "draft_meta_info.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    (project_dir / "plan.txt").write_text(_build_news_plan_txt(news_script), encoding="utf-8")

    _update_root_meta(project_dir, project_name, draft_id, news_script.title)

    backup = Path(output_dir) / project_name
    if str(project_dir) != str(backup):
        if backup.exists():
            shutil.rmtree(backup)
        shutil.copytree(project_dir, backup)

    print(f"  뉴스 CapCut 프로젝트 생성 완료: {project_dir}")
    return str(project_dir)


def _build_news_plan_txt(script) -> str:
    lines = [
        f"제목: {script.title}",
        f"설명: {script.description}",
        f"해시태그: {' '.join(script.hashtags)}",
        "",
        "── 구성 ──",
    ]
    for i, seg in enumerate(script.segments, 1):
        role = getattr(seg, "role", "body").upper()
        pivot = getattr(seg, "pivot_phrase", "") or ""
        emph = getattr(seg, "emphasis_words", []) or []
        header = f"[{i}] {role} | {seg.media_type.upper()} | {seg.duration:.1f}s"
        if pivot:
            header += f" | pivot: '{pivot}'"
        header += f" | 키워드: {seg.search_keyword or '-'}"
        lines.append(header)
        lines.append(f"     텍스트: {seg.text_content}")
        if emph:
            lines.append(f"     강조: {', '.join(emph)}")
        lines.append(f"     자막: {seg.caption}")
    return "\n".join(lines)


# ── 기존 파이프라인 호환 (SelectedClip 리스트) ─────────────────────────────────

def export_to_capcut(
    video_path: str,
    clips: list[SelectedClip],
    output_dir: str = "output/capcut",
) -> list[str]:
    from src.selector.claude_selector import ShortsScript, ScriptSegment
    results = []
    for i, clip in enumerate(clips, 1):
        script = ShortsScript(
            title=clip.hook,
            description=" ".join(clip.hashtags),
            hashtags=clip.hashtags,
            segments=[ScriptSegment(
                start=clip.start, end=clip.end,
                caption=clip.hook, text_overlay="", role="content",
            )],
        )
        stem = Path(video_path).stem
        results.append(export_script_to_capcut(
            video_path=video_path,
            script=script,
            output_dir=output_dir,
        ))
    return results
