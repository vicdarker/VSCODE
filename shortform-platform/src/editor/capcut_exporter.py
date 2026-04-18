import json
import uuid
import os
import time
from pathlib import Path

from src.selector.claude_selector import SelectedClip


def _create_uuid() -> str:
    return str(uuid.uuid4()).upper()


def export_to_capcut(video_path: str, clips: list[SelectedClip], output_dir: str = "output/capcut") -> list[str]:
    """
    선택된 클립들을 각각의 캡컷(CapCut) 프로젝트 풀더로 생성합니다.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    stem = Path(video_path).stem
    results = []

    # 캡컷은 보통 절대 경로 + '/' 슬래시를 사용합니다.
    abs_video_path = os.path.abspath(video_path).replace("\\", "/")
    
    for i, clip in enumerate(clips, 1):
        project_name = f"{stem}_clip{i:02d}"
        project_dir = out_dir / project_name
        project_dir.mkdir(parents=True, exist_ok=True)
        
        # 캡컷은 시간을 마이크로초(1/1,000,000초) 단위로 기록합니다.
        duration_us = int((clip.end - clip.start) * 1000000)
        start_us = int(clip.start * 1000000)
        
        material_id = _create_uuid()
        segment_id = _create_uuid()
        track_id = _create_uuid()
        
        # 1. draft_content.json 구성
        content = {
            "canvas_config": {"height": 1920, "width": 1080, "ratio": "9:16"},
            "materials": {
                "audios": [], "transitions": [], "texts": [], "effects": [], "filters": [],
                "videos": [
                    {
                        "id": material_id,
                        "path": abs_video_path,
                        "material_name": Path(video_path).name,
                        "type": "video",
                        "duration": duration_us, 
                    }
                ]
            },
            "tracks": [
                {
                    "attribute": 0, "flag": 0, "id": track_id, "type": "video",
                    "segments": [
                        {
                            "id": segment_id,
                            "material_id": material_id,
                            "source_timerange": {"duration": duration_us, "start": start_us},
                            "target_timerange": {"duration": duration_us, "start": 0}
                        }
                    ]
                }
            ],
            "version": 1
        }
        
        # 2. draft_meta_info.json 구성
        cur_time = int(time.time() * 1000)
        meta = {
            "id": _create_uuid(),
            "draft_name": project_name,
            "draft_materials": [
                {
                    "value": [
                        {
                            "file_Path": abs_video_path,
                            "file_id": material_id,
                            "file_name": Path(video_path).name
                        }
                    ]
                }
            ],
            "tm_draft_create": cur_time,
            "tm_draft_modified": cur_time
        }
        
        # 파일 저장
        with open(project_dir / "draft_content.json", "w", encoding="utf-8") as f:
            json.dump(content, f, indent=2, ensure_ascii=False)
            
        with open(project_dir / "draft_meta_info.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
            
        results.append(str(project_dir))
        print(f"  [clip {i}] CapCut 프로젝트 생성 완료: {project_dir}")
        
    return results
