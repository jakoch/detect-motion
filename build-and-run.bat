@echo off

@rem Build the Docker image
docker build -t detect-motion:latest -f .devcontainer\Dockerfile .

@rem Smoke test
docker run --rm detect-motion:latest --version

@rem This should answer with the version of the application:
@rem Simple Motion Detector v2.0.0
@rem Copy right (c) 2025-2026 Jens A. Koch

@rem Run the application on the video folder
run-detect-motion.bat "D:\video"

@rem Videos with motion detected land in "D:\video-keep"
@rem Videos without motion land in "D:\video-drop"
@rem Report lands in "D:\video-keep\motion-report.json"