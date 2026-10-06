import os
import sys
import json
import time
import argparse
from pathlib import Path
import cv2

# Ensure UTF-8 output encoding
if sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def process_video(
    source_path,
    weights_path,
    output_video_path=None,
    output_json_path=None,
    conf_thresh=0.25,
    iou_thresh=0.45,
    device=None,
    show_progress=True,
):
    """
    Offline/batch video inference using streaming inference (stream=True).
    Avoids memory leaks on long video files by processing frame-by-frame.
    """
    from ultralytics import YOLO

    source_path = Path(source_path)
    if not source_path.exists():
        raise FileNotFoundError(f"Video file not found: {source_path}")

    print(f"Loading model: {weights_path}")
    model = YOLO(str(weights_path))

    cap = cv2.VideoCapture(str(source_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video file: {source_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration_sec = total_frames / fps if fps > 0 else 0

    print(f"Video Info: {width}x{height} @ {fps:.2f} FPS | Total frames: {total_frames} (~{duration_sec:.1f}s)")
    cap.release()

    video_writer = None
    if output_video_path:
        out_p = Path(output_video_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        video_writer = cv2.VideoWriter(str(out_p), fourcc, fps, (width, height))
        print(f"Annotated output video will be written to: {out_p}")

    # Use stream=True as mandated by Section 5 Phase 4 of Technical Spec
    print("Running batch streaming inference (stream=True)...")
    results = model.predict(
        source=str(source_path),
        stream=True,
        conf=conf_thresh,
        iou=iou_thresh,
        device=device,
        verbose=False,
    )

    frame_detections = []
    smoking_intervals = []
    current_interval_start = None
    total_smoking_frames = 0
    start_time = time.time()

    for frame_idx, r in enumerate(results):
        timestamp = frame_idx / fps if fps > 0 else 0.0
        boxes = r.boxes
        has_detection = boxes is not None and len(boxes) > 0

        frame_info = {
            "frame_idx": frame_idx,
            "timestamp_sec": round(timestamp, 3),
            "detections": [],
        }

        if has_detection:
            total_smoking_frames += 1
            if current_interval_start is None:
                current_interval_start = timestamp

            for b in boxes:
                xyxy = b.xyxy[0].tolist()
                conf = float(b.conf[0])
                cls_id = int(b.cls[0])
                cls_name = r.names.get(cls_id, "smoke")
                frame_info["detections"].append({
                    "box": [round(x, 1) for x in xyxy],
                    "confidence": round(conf, 4),
                    "class": cls_name,
                })
        else:
            if current_interval_start is not None:
                smoking_intervals.append({
                    "start_sec": round(current_interval_start, 2),
                    "end_sec": round(timestamp, 2),
                    "duration_sec": round(timestamp - current_interval_start, 2),
                })
                current_interval_start = None

        if frame_info["detections"]:
            frame_detections.append(frame_info)

        if video_writer is not None:
            annotated_frame = r.plot()
            video_writer.write(annotated_frame)

        if show_progress and total_frames > 0 and (frame_idx + 1) % 100 == 0:
            pct = (frame_idx + 1) / total_frames * 100
            elapsed = time.time() - start_time
            fps_proc = (frame_idx + 1) / elapsed if elapsed > 0 else 0
            print(f"Processed {frame_idx + 1}/{total_frames} frames ({pct:.1f}%) - Speed: {fps_proc:.1f} FPS")

    # Finalize any open interval
    if current_interval_start is not None:
        smoking_intervals.append({
            "start_sec": round(current_interval_start, 2),
            "end_sec": round(duration_sec, 2),
            "duration_sec": round(duration_sec - current_interval_start, 2),
        })

    if video_writer is not None:
        video_writer.release()
        print(f"Video writer closed. Saved annotated video.")

    elapsed_total = time.time() - start_time
    avg_fps = (total_frames / elapsed_total) if elapsed_total > 0 else 0

    summary = {
        "source": str(source_path),
        "total_frames": total_frames,
        "duration_sec": round(duration_sec, 2),
        "total_smoking_frames": total_smoking_frames,
        "smoking_frame_percentage": round((total_smoking_frames / total_frames * 100) if total_frames > 0 else 0, 2),
        "smoking_detected": total_smoking_frames > 0,
        "smoking_intervals": smoking_intervals,
        "processing_time_sec": round(elapsed_total, 2),
        "processing_fps": round(avg_fps, 2),
        "detections_detail": frame_detections,
    }

    if output_json_path:
        out_j = Path(output_json_path)
        out_j.parent.mkdir(parents=True, exist_ok=True)
        out_j.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Saved detection summary to: {out_j}")

    print("\n" + "=" * 50)
    print("Video Processing Complete")
    print(f"Smoking detected: {'YES' if summary['smoking_detected'] else 'NO'}")
    print(f"Total smoking intervals: {len(smoking_intervals)}")
    for idx, interval in enumerate(smoking_intervals, 1):
        print(f"  • Event {idx}: {interval['start_sec']}s -> {interval['end_sec']}s ({interval['duration_sec']}s)")
    print(f"Processing Speed: {avg_fps:.1f} FPS")
    print("=" * 50)
    return summary

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Offline Video Smoking Detection (Streaming Inference)")
    parser.add_argument("--source", type=str, required=True, help="Path to input video file")
    parser.add_argument("--weights", type=str, default="runs/detect/smoke_p2/weights/best.pt", help="Path to model weights")
    parser.add_argument("--save-vid", type=str, default=None, help="Path to save annotated output video")
    parser.add_argument("--save-json", type=str, default=None, help="Path to save detection summary JSON")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold")
    parser.add_argument("--device", type=str, default=None, help="Device (cpu, 0, etc.)")

    args = parser.parse_args()
    process_video(
        source_path=args.source,
        weights_path=args.weights,
        output_video_path=args.save_vid,
        output_json_path=args.save_json,
        conf_thresh=args.conf,
        device=args.device,
    )
