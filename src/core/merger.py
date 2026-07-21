import os
import subprocess

from src.utils.config import Config


class Merger:
    """视频合并器，使用ffmpeg将ts片段合并为完整的视频文件。"""

    def __init__(self, ffmpeg_path=None):
        """初始化合并器。

        Args:
            ffmpeg_path: ffmpeg可执行文件路径，默认使用Config.DEFAULT_FFMPEG_PATH
        """
        self.ffmpeg_path = ffmpeg_path or Config.DEFAULT_FFMPEG_PATH

    def merge(self, ts_files, output_path):
        """合并ts片段列表为完整视频。

        使用ffmpeg的concat demuxer方式：先生成filelist.txt，再调用ffmpeg合并。

        Args:
            ts_files: ts 片段文件路径列表（按播放顺序）
            output_path: 合并后输出文件路径（默认mp4格式）

        Returns:
            bool: 合并是否成功
        """
        if not ts_files:
            return False

        # 输出路径默认为mp4格式：无扩展名时补 .mp4
        if not os.path.splitext(output_path)[1]:
            output_path = output_path + ".mp4"

        out_dir = os.path.dirname(os.path.abspath(output_path))
        os.makedirs(out_dir, exist_ok=True)

        # 生成 concat 格式的文件列表
        filelist_path = os.path.join(out_dir, "filelist.txt")
        if not self._write_filelist(ts_files, filelist_path):
            # 生成列表失败（如片段文件不存在），清理后返回
            self._safe_remove(filelist_path)
            return False

        success = False
        try:
            success = self.merge_with_filelist(filelist_path, output_path)
        finally:
            # 无论成功与否都清理临时filelist
            self._safe_remove(filelist_path)

        if not success:
            return False

        # 合并成功后清理临时ts文件
        for ts in ts_files:
            self._safe_remove(ts)

        return True

    def merge_with_filelist(self, filelist_path, output_path):
        """使用ffmpeg concat 播放列表文件合并视频。

        Args:
            filelist_path: concat 列表文件路径
            output_path: 合并后输出文件路径

        Returns:
            bool: 合并是否成功
        """
        if not os.path.exists(filelist_path):
            return False

        out_dir = os.path.dirname(os.path.abspath(output_path))
        os.makedirs(out_dir, exist_ok=True)

        # 先尝试带 AAC bitstream filter 的命令（处理HLS中常见的ADTS封装），
        # 失败则回退到纯流拷贝命令（兼容无音频或非AAC流）
        cmd_with_bsf = self._build_command(filelist_path, output_path, with_bsf=True)
        cmd_plain = self._build_command(filelist_path, output_path, with_bsf=False)

        for cmd in (cmd_with_bsf, cmd_plain):
            if self._run_ffmpeg(cmd):
                # 命令成功且输出文件已生成
                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    return True
                # 输出异常则清理后尝试下一个命令
                self._safe_remove(output_path)
            else:
                # 失败时清理可能产生的不完整输出
                self._safe_remove(output_path)

        return False

    def _build_command(self, filelist_path, output_path, with_bsf):
        """构造ffmpeg concat 合并命令。"""
        cmd = [
            self.ffmpeg_path,
            "-y",                       # 覆盖已存在的输出文件
            "-f", "concat",
            "-safe", "0",               # 允许绝对路径及特殊字符
            "-i", filelist_path,
            "-c", "copy",               # 直接拷贝流，不重新编码，速度最快
        ]
        if with_bsf:
            # 处理ts中AAC的ADTS头转ASC，mp4容器需要
            cmd.extend(["-bsf:a", "aac_adtstoasc"])
        cmd.append(output_path)
        return cmd

    def _run_ffmpeg(self, cmd):
        """调用ffmpeg并返回是否执行成功（returncode == 0）。"""
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=self._get_creation_flags(),
            )
        except (OSError, subprocess.SubprocessError):
            # ffmpeg不可用或调用异常
            return False
        return result.returncode == 0

    @staticmethod
    def _write_filelist(ts_files, filelist_path):
        """生成ffmpeg concat格式的filelist.txt。

        每行格式: file '路径'，单引号包裹可正确处理空格等特殊字符。
        """
        try:
            with open(filelist_path, "w", encoding="utf-8") as f:
                for ts in ts_files:
                    if not os.path.exists(ts):
                        return False
                    # 使用绝对路径，统一为正斜杠避免反斜杠转义问题
                    abs_path = os.path.abspath(ts).replace("\\", "/")
                    # 转义路径中可能存在的单引号: ' -> '\''
                    safe_path = abs_path.replace("'", "'\\''")
                    f.write(f"file '{safe_path}'\n")
        except OSError:
            return False
        return True

    @staticmethod
    def _safe_remove(path):
        """安全删除文件，忽略不存在或权限错误。"""
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except OSError:
            pass

    @staticmethod
    def _get_creation_flags():
        """获取subprocess创建标志（Windows下隐藏控制台窗口）。"""
        if os.name == "nt":
            # CREATE_NO_WINDOW，避免弹出黑色控制台窗口
            return 0x08000000
        return 0
