"""
hardware.py: Cross-Platform Hardware Detection and Compute Device Selection.
Supports CPU and GPUs across Windows, Linux, and macOS.
"""
import os
import sys
import platform
import subprocess
import shutil
from typing import List, Dict, Any

class HardwareDetector:
    """Detects available compute devices (CPU, NVIDIA, AMD, Intel, Apple Silicon)."""

    @classmethod
    def get_cpu_info(cls) -> Dict[str, Any]:
        """Returns detected CPU name and logical core count."""
        cores = os.cpu_count() or 4
        proc_name = platform.processor() or "Multi-Core CPU"
        
        # Try friendly CPU name on Windows
        if platform.system() == "Windows":
            try:
                cmd = 'powershell -NoProfile -Command "(Get-CimInstance Win32_Processor).Name"'
                res = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL)
                first_line = res.strip().splitlines()[0].strip()
                if first_line:
                    proc_name = first_line
            except Exception:
                pass
        elif platform.system() == "Linux":
            try:
                with open("/proc/cpuinfo", "r") as f:
                    for line in f:
                        if "model name" in line:
                            proc_name = line.split(":", 1)[1].strip()
                            break
            except Exception:
                pass
        elif platform.system() == "Darwin":
            try:
                res = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True)
                if res.strip():
                    proc_name = res.strip()
            except Exception:
                pass

        return {
            "id": "cpu",
            "name": f"💻 CPU: {proc_name} ({cores} Cores)",
            "type": "cpu",
            "num_gpu": 0,
            "recommended": True
        }

    @classmethod
    def get_gpu_devices(cls) -> List[Dict[str, Any]]:
        """Detects available GPUs across NVIDIA, AMD, Intel, and Apple Silicon."""
        gpus: List[Dict[str, Any]] = []

        # 1. Check NVIDIA via nvidia-smi
        nvidia_smi = shutil.which("nvidia-smi")
        if nvidia_smi:
            try:
                cmd = [nvidia_smi, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"]
                out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
                for idx, line in enumerate(out.strip().splitlines()):
                    if line.strip():
                        parts = line.split(",")
                        gpu_name = parts[0].strip()
                        gpu_mem = f"{parts[1].strip()} MB" if len(parts) > 1 else ""
                        gpus.append({
                            "id": f"gpu_nvidia_{idx}",
                            "name": f"🎮 NVIDIA GPU: {gpu_name} ({gpu_mem})",
                            "type": "nvidia",
                            "num_gpu": 99,
                            "recommended": True
                        })
            except Exception:
                pass

        # 2. Check Windows GPUs via CIM (Intel Arc/Xe/iGPU, AMD Radeon)
        if platform.system() == "Windows":
            try:
                cmd = 'powershell -NoProfile -Command "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"'
                out = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL)
                for line in out.strip().splitlines():
                    name = line.strip()
                    if name and not any(g["name"].find(name) != -1 for g in gpus):
                        is_intel = "intel" in name.lower()
                        gpus.append({
                            "id": f"gpu_win_{len(gpus)}",
                            "name": f"🎮 GPU: {name}",
                            "type": "intel" if is_intel else "gpu",
                            "num_gpu": 99 if not is_intel else 33,
                            "recommended": not is_intel
                        })
            except Exception:
                pass

        # 3. Check Linux GPUs via lspci
        if platform.system() == "Linux" and not gpus:
            lspci = shutil.which("lspci")
            if lspci:
                try:
                    out = subprocess.check_output(f"{lspci} | grep -E 'VGA|3D|Display'", shell=True, text=True)
                    for line in out.strip().splitlines():
                        if ":" in line:
                            desc = line.split(":", 2)[-1].strip()
                            gpus.append({
                                "id": f"gpu_linux_{len(gpus)}",
                                "name": f"🎮 GPU: {desc}",
                                "type": "gpu",
                                "num_gpu": 99,
                                "recommended": True
                            })
                except Exception:
                    pass

        # 4. Check Apple Silicon MPS
        if platform.system() == "Darwin" and platform.processor() == "arm":
            gpus.append({
                "id": "gpu_apple_metal",
                "name": "⚡ Apple Silicon Metal (MPS GPU)",
                "type": "apple",
                "num_gpu": 99,
                "recommended": True
            })

        return gpus

    @classmethod
    def get_all_compute_options(cls) -> List[Dict[str, Any]]:
        """Returns ordered list of available compute options (CPU + all detected GPUs)."""
        options = [cls.get_cpu_info()]
        options.extend(cls.get_gpu_devices())
        return options

def get_hardware_options() -> List[Dict[str, Any]]:
    """Returns list of compute device options."""
    return HardwareDetector.get_all_compute_options()

def get_hardware_info() -> Dict[str, Any]:
    """Returns dictionary of CPU and GPU info."""
    return {
        "cpu": HardwareDetector.get_cpu_info(),
        "gpus": HardwareDetector.get_gpu_devices(),
        "options": HardwareDetector.get_all_compute_options()
    }
