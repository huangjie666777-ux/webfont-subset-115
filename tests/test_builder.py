from pathlib import Path

from app import config, storage
from app.fonts import validate_font
from app.planner import collect_codepoints, plan_fallback
from app import builder


def test_failure_cleans_staging():
    storage.init_dirs()
    data = Path("examples/fonts/DejaVuSans.ttf").read_bytes()
    info = validate_font(data)
    storage.save_font_if_absent(
        info.font_id,
        data,
        {
            "font_id": info.font_id,
            "filename": "x",
            "family": info.family,
            "original_size": info.original_size,
            "weight": info.weight,
            "style": info.style,
        },
    )
    plan = plan_fallback([ord("A")], [info.font_id], {info.font_id: info.codepoints})

    before = set(config.TMP_DIR.glob("build-*"))

    # Force subsetting to fail by pointing at a nonexistent source after plan.
    real = storage.font_path(info.font_id)
    staged = real.read_bytes()
    real.unlink()
    try:
        job_id = builder.new_job_id()
        job = builder.run_build(job_id, plan)
        assert job.status == "failed"
        assert not (config.TMP_DIR / f"build-{job_id}").exists()
        assert builder.package_path(job_id) is None
        assert set(config.TMP_DIR.glob("build-*")) == before
    finally:
        real.write_bytes(staged)
