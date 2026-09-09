using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text.RegularExpressions;
using System.Windows.Forms;

internal static class Launcher
{
    private static string Quote(string value)
    {
        return "\"" + Regex.Replace(value, "(\\\\*)\"", "$1$1\\\"")
            .TrimEnd('\\') + new string('\\', value.Length - value.TrimEnd('\\').Length) +
            new string('\\', value.Length - value.TrimEnd('\\').Length) + "\"";
    }

    [STAThread]
    private static int Main(string[] args)
    {
        try
        {
            string root = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
            string python = Path.Combine(root, "runtime", "pythonw.exe");
            if (!File.Exists(python) || !File.Exists(Path.Combine(root, "main.py")))
                throw new IOException("请先完整解压便携包；exe 需要同目录的 runtime 和程序文件。");
            string arguments = "main.py";
            foreach (string argument in args) arguments += " " + Quote(argument);
            var info = new ProcessStartInfo(python, arguments);
            info.WorkingDirectory = root;
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            info.EnvironmentVariables.Remove("PYTHONHOME");
            info.EnvironmentVariables.Remove("PYTHONPATH");
            info.EnvironmentVariables["PYTHONNOUSERSITE"] = "1";
            info.EnvironmentVariables["PYTHONUTF8"] = "1";
            using (var process = Process.Start(info))
            {
                process.WaitForExit();
                if (process.ExitCode != 0)
                    MessageBox.Show("程序异常退出，请查看 logs 目录。", "ok-wows");
                return process.ExitCode;
            }
        }
        catch (Exception error)
        {
            MessageBox.Show(error.Message, "ok-wows 启动失败", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}
