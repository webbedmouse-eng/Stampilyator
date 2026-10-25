using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

[assembly: AssemblyTitle("Штампилятор — загрузчик")]
[assembly: AssemblyDescription("Загружает рабочие файлы Штампилятора при первом запуске")]
[assembly: AssemblyProduct("Штампилятор")]
[assembly: AssemblyCompany("Volgodonsk")]
[assembly: AssemblyVersion("1.3.0.0")]
[assembly: AssemblyFileVersion("1.3.0.0")]

namespace ShtampilyatorBootstrap
{
    internal static class Program
    {
        internal const string Version = "1.3.0";
        internal const string AppExe = "Штампилятор.exe";
        internal const string DefaultUrl =
            "https://github.com/webbedmouse-eng/Stampilyator/releases/download/v1.3.0/runtime-1.3.0.zip";
        internal const string DefaultSha256 =
            "4d12c5ae20c92abd0f763d12fe546469899bff9f2974b576577470c990c58fe2";

        private static string _dataRoot;
        private static string _runtimeRoot;

        internal static string DataRoot
        {
            get
            {
                if (_dataRoot == null)
                {
                    _dataRoot = Path.Combine(
                        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                        "Shtampilyator"
                    );
                }
                return _dataRoot;
            }
        }

        internal static void Configure(string[] args)
        {
            string custom = ReadArgument(args, "--data-dir");
            if (String.IsNullOrEmpty(custom))
            {
                custom = Environment.GetEnvironmentVariable("SHTAMPILYATOR_DATA_DIR");
            }
            if (!String.IsNullOrEmpty(custom))
            {
                _dataRoot = Path.GetFullPath(custom);
            }
        }

        internal static string RuntimeRoot
        {
            get
            {
                if (_runtimeRoot != null)
                {
                    return _runtimeRoot;
                }
                string installed = FindInstalledRuntime();
                if (installed != null)
                {
                    return installed;
                }
                return Path.Combine(DataRoot, "runtime", Version);
            }
        }

        private static string[] InstallRoots()
        {
            return new string[]
            {
                DataRoot,
                AppDomain.CurrentDomain.BaseDirectory,
                Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
                    "Shtampilyator"
                )
            };
        }

        internal static string FindInstalledRuntime()
        {
            foreach (string root in InstallRoots())
            {
                try
                {
                    string candidate = Path.Combine(root, "runtime", Version);
                    if (File.Exists(Path.Combine(candidate, AppExe)))
                    {
                        _runtimeRoot = candidate;
                        return candidate;
                    }
                }
                catch
                {
                    // Проверяем следующий вариант.
                }
            }
            return null;
        }

        internal static bool InstalledHashMatches(string expected)
        {
            try
            {
                string marker = Path.Combine(RuntimeRoot, ".runtime.sha256");
                if (!File.Exists(AppPath) || !File.Exists(marker))
                {
                    return false;
                }
                return String.Equals(
                    File.ReadAllText(marker).Trim(),
                    expected.Trim(),
                    StringComparison.OrdinalIgnoreCase
                );
            }
            catch
            {
                return false;
            }
        }

        internal static string ChooseInstallRuntime()
        {
            foreach (string root in InstallRoots())
            {
                string candidate = Path.Combine(root, "runtime", Version);
                try
                {
                    if (Directory.Exists(candidate))
                    {
                        Directory.Delete(candidate, true);
                    }
                    Directory.CreateDirectory(candidate);
                    string probe = Path.Combine(
                        candidate,
                        ".write-" + Guid.NewGuid().ToString("N")
                    );
                    File.WriteAllText(probe, "ok");
                    File.Delete(probe);
                    Directory.Delete(candidate, true);
                    _runtimeRoot = candidate;
                    return candidate;
                }
                catch
                {
                    // Пробуем следующий каталог.
                }
            }
            throw new UnauthorizedAccessException(
                "Не удалось найти папку для установки. Разместите загрузчик "
                    + "в папке «Документы» или «Загрузки»."
            );
        }

        internal static string AppPath
        {
            get { return Path.Combine(RuntimeRoot, AppExe); }
        }

        private static string ConfigPath(string name)
        {
            return Path.Combine(AppDomain.CurrentDomain.BaseDirectory, name);
        }

        internal static string ResolveUrl(string[] args)
        {
            string fromArgs = ReadArgument(args, "--url");
            if (!String.IsNullOrEmpty(fromArgs))
            {
                return fromArgs;
            }
            string fromFile = ReadFirstLine(ConfigPath("runtime.url"));
            return String.IsNullOrEmpty(fromFile) ? DefaultUrl : fromFile;
        }

        internal static string ResolveHash(string[] args)
        {
            string fromArgs = ReadArgument(args, "--sha256");
            if (!String.IsNullOrEmpty(fromArgs))
            {
                return fromArgs.Trim();
            }
            string fromFile = ReadFirstLine(ConfigPath("runtime.sha256"));
            return String.IsNullOrEmpty(fromFile) ? DefaultSha256 : fromFile.Trim();
        }

        private static string ReadArgument(string[] args, string name)
        {
            if (args == null)
            {
                return null;
            }
            for (int i = 0; i < args.Length; i++)
            {
                if (String.Equals(args[i], name, StringComparison.OrdinalIgnoreCase)
                    && i + 1 < args.Length)
                {
                    return args[i + 1];
                }
            }
            return null;
        }

        private static string ReadFirstLine(string path)
        {
            try
            {
                if (!File.Exists(path))
                {
                    return null;
                }
                foreach (string line in File.ReadAllLines(path))
                {
                    string value = line.Trim();
                    if (value.Length > 0 && !value.StartsWith("#"))
                    {
                        return value;
                    }
                }
            }
            catch
            {
                // Конфигурация необязательна.
            }
            return null;
        }

        internal static void Log(string message)
        {
            try
            {
                Directory.CreateDirectory(DataRoot);
                File.AppendAllText(
                    Path.Combine(DataRoot, "bootstrap.log"),
                    DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + " " + message + Environment.NewLine
                );
            }
            catch
            {
                // Загрузчик не должен падать из-за журнала.
            }
        }

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern bool DeleteFile(string fileName);

        internal static void UnblockTree(string root)
        {
            try
            {
                foreach (string file in Directory.GetFiles(root, "*", SearchOption.AllDirectories))
                {
                    // Снимаем метку «файл из интернета» только после проверки SHA-256.
                    DeleteFile(file + ":Zone.Identifier");
                }
            }
            catch
            {
                // Метка не критична; приложение всё равно можно запустить.
            }
        }

        internal static void Launch()
        {
            if (!File.Exists(AppPath))
            {
                throw new FileNotFoundException("Не найден файл приложения.", AppPath);
            }
            ProcessStartInfo info = new ProcessStartInfo(AppPath);
            info.UseShellExecute = true;
            info.WorkingDirectory = RuntimeRoot;
            Process.Start(info);
        }

        [STAThread]
        internal static void Main(string[] args)
        {
            Configure(args);
            ServicePointManager.SecurityProtocol |= SecurityProtocolType.Tls12;
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            if (
                FindInstalledRuntime() != null
                && File.Exists(AppPath)
                && InstalledHashMatches(ResolveHash(args))
            )
            {
                try
                {
                    Launch();
                    return;
                }
                catch (Exception ex)
                {
                    Log("Не удалось запустить установленную версию: " + ex);
                }
            }

            Application.Run(new LoaderForm(args));
        }
    }

    internal sealed class LoaderForm : Form
    {
        private readonly string _url;
        private readonly string _sha256;
        private readonly Label _status;
        private readonly ProgressBar _progress;
        private readonly Button _button;
        private CancellationTokenSource _cancellation;
        private bool _downloading;

        internal LoaderForm(string[] args)
        {
            _url = Program.ResolveUrl(args);
            _sha256 = Program.ResolveHash(args);

            Text = "Штампилятор 1.3.0";
            ClientSize = new Size(570, 245);
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            MinimizeBox = false;
            StartPosition = FormStartPosition.CenterScreen;
            BackColor = Color.FromArgb(247, 249, 252);
            Font = new Font("Segoe UI", 9.0f);
            try
            {
                Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
            }
            catch
            {
                // Иконка не критична.
            }

            Label title = new Label();
            title.Text = "Штампилятор";
            title.Font = new Font("Segoe UI Semibold", 16.0f);
            title.ForeColor = Color.FromArgb(18, 35, 61);
            title.AutoSize = true;
            title.Location = new Point(24, 20);
            Controls.Add(title);

            Label subtitle = new Label();
            subtitle.Text = "Первый запуск: загрузка рабочих файлов";
            subtitle.ForeColor = Color.FromArgb(91, 108, 132);
            subtitle.AutoSize = true;
            subtitle.Location = new Point(27, 56);
            Controls.Add(subtitle);

            _status = new Label();
            _status.Text = "Подготовка…";
            _status.ForeColor = Color.FromArgb(49, 68, 95);
            _status.AutoEllipsis = true;
            _status.Location = new Point(27, 92);
            _status.Size = new Size(516, 22);
            Controls.Add(_status);

            _progress = new ProgressBar();
            _progress.Location = new Point(27, 120);
            _progress.Size = new Size(516, 18);
            _progress.Style = ProgressBarStyle.Continuous;
            _progress.Minimum = 0;
            _progress.Maximum = 1000;
            Controls.Add(_progress);

            Label hint = new Label();
            hint.Text = "Загрузится около 87 МБ. После установки интернет не требуется.";
            hint.ForeColor = Color.FromArgb(124, 138, 157);
            hint.AutoSize = true;
            hint.Location = new Point(27, 148);
            Controls.Add(hint);

            _button = new Button();
            _button.Text = "Отмена";
            _button.Size = new Size(112, 32);
            _button.Location = new Point(431, 190);
            _button.Click += ButtonClick;
            Controls.Add(_button);

            Shown += OnShown;
            FormClosing += OnFormClosing;
        }

        private async void OnShown(object sender, EventArgs e)
        {
            await StartAsync();
        }

        private async void ButtonClick(object sender, EventArgs e)
        {
            if (_downloading && _cancellation != null)
            {
                _cancellation.Cancel();
                _button.Enabled = false;
                return;
            }
            await StartAsync();
        }

        private void Report(int value, string text)
        {
            if (IsDisposed || !IsHandleCreated)
            {
                return;
            }
            if (InvokeRequired)
            {
                BeginInvoke(new Action<int, string>(Report), value, text);
                return;
            }
            _progress.Value = Math.Max(0, Math.Min(1000, value));
            if (!String.IsNullOrEmpty(text))
            {
                _status.Text = text;
            }
        }

        private static string PickWorkDirectory()
        {
            string[] candidates = new string[]
            {
                Path.Combine(Program.DataRoot, "downloads"),
                AppDomain.CurrentDomain.BaseDirectory,
                Path.GetTempPath()
            };
            foreach (string candidate in candidates)
            {
                try
                {
                    Directory.CreateDirectory(candidate);
                    string probe = Path.Combine(
                        candidate,
                        ".write-" + Guid.NewGuid().ToString("N")
                    );
                    File.WriteAllText(probe, "ok");
                    File.Delete(probe);
                    return candidate;
                }
                catch
                {
                    // Пробуем следующий каталог.
                }
            }
            throw new UnauthorizedAccessException(
                "Нет доступной папки для загрузки. Разместите загрузчик в папке, "
                    + "куда можно записывать файлы."
            );
        }

        private string GetCachePath(string workDir)
        {
            string baseName = Path.Combine(workDir, "Shtampilyator-" + Program.Version);
            string path = baseName + ".zip";
            if (File.Exists(path))
            {
                if (HashMatches(path, _sha256))
                {
                    return path;
                }
                try
                {
                    File.Delete(path);
                }
                catch
                {
                    return baseName + "-" + Guid.NewGuid().ToString("N") + ".zip";
                }
            }
            return path;
        }

        private async Task StartAsync()
        {
            if (_downloading)
            {
                return;
            }
            _downloading = true;
            _button.Enabled = true;
            _button.Text = "Отмена";
            _cancellation = new CancellationTokenSource();
            try
            {
                Directory.CreateDirectory(Program.DataRoot);
                string workDir = PickWorkDirectory();
                string zipPath = GetCachePath(workDir);
                Program.Log("Старт загрузки: " + _url);
                Program.Log("Каталог загрузки: " + workDir);

                if (!File.Exists(zipPath))
                {
                    await DownloadAsync(zipPath, _cancellation.Token);
                }
                else
                {
                    Report(850, "Используется ранее загруженный архив");
                }

                if (!HashMatches(zipPath, _sha256))
                {
                    throw new InvalidDataException(
                        "Контрольная сумма архива не совпала. Файл повреждён или был подменён."
                    );
                }

                Report(900, "Распаковка…");
                string extractRoot = Path.Combine(
                    workDir,
                    "install-" + Guid.NewGuid().ToString("N")
                );
                try
                {
                    Directory.CreateDirectory(extractRoot);
                    ZipFile.ExtractToDirectory(zipPath, extractRoot);
                    string found = Directory
                        .GetFiles(extractRoot, Program.AppExe, SearchOption.AllDirectories)
                        .FirstOrDefault();
                    if (found == null)
                    {
                        throw new InvalidDataException(
                            "В загруженном архиве не найден " + Program.AppExe + "."
                        );
                    }
                    string sourceDir = Path.GetDirectoryName(found);
                    string target = Program.ChooseInstallRuntime();
                    MoveOrCopyDirectory(sourceDir, target);
                    File.WriteAllText(
                        Path.Combine(Program.RuntimeRoot, ".runtime.sha256"),
                        _sha256
                    );
                }
                finally
                {
                    TryDeleteDirectory(extractRoot);
                }

                if (!File.Exists(Program.AppPath))
                {
                    throw new FileNotFoundException(
                        "После распаковки не найден файл приложения.",
                        Program.AppPath
                    );
                }

                Program.Log("Установлено: " + Program.RuntimeRoot);
                Program.UnblockTree(Program.RuntimeRoot);
                Report(1000, "Готово. Запускаем…");
                await Task.Delay(150);
                Program.Launch();
                Close();
            }
            catch (OperationCanceledException)
            {
                Program.Log("Загрузка отменена пользователем.");
                Close();
            }
            catch (Exception ex)
            {
                _downloading = false;
                Program.Log("Ошибка: " + ex);
                Report(0, "Не удалось загрузить приложение");
                _button.Text = "Повторить";
                _button.Enabled = true;
                MessageBox.Show(
                    this,
                    "Не удалось получить рабочие файлы.\n\n"
                        + ex.Message
                        + "\n\nИсточник:\n"
                        + _url
                        + "\n\nЖурнал:\n"
                        + Path.Combine(Program.DataRoot, "bootstrap.log"),
                    "Ошибка запуска",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error
                );
            }
            finally
            {
                _downloading = false;
            }
        }

        private async Task DownloadAsync(string destination, CancellationToken token)
        {
            string partPath = destination + "." + Guid.NewGuid().ToString("N") + ".part";
            using (HttpClient client = new HttpClient())
            {
                client.Timeout = TimeSpan.FromMinutes(30);
                client.DefaultRequestHeaders.UserAgent.ParseAdd(
                    "ShtampilyatorBootstrap/1.3.0"
                );
                using (
                    HttpResponseMessage response = await client.GetAsync(
                        _url,
                        HttpCompletionOption.ResponseHeadersRead,
                        token
                    )
                )
                {
                    response.EnsureSuccessStatusCode();
                    long total = response.Content.Headers.ContentLength ?? -1;
                    using (Stream input = await response.Content.ReadAsStreamAsync())
                    using (
                        FileStream output = new FileStream(
                            partPath,
                            FileMode.Create,
                            FileAccess.Write,
                            FileShare.None,
                            81920,
                            true
                        )
                    )
                    {
                        byte[] buffer = new byte[81920];
                        long received = 0;
                        int read;
                        while ((read = await input.ReadAsync(buffer, 0, buffer.Length, token)) > 0)
                        {
                            await output.WriteAsync(buffer, 0, read, token);
                            received += read;
                            if (total > 0)
                            {
                                int percent = (int)(received * 850L / total);
                                Report(
                                    percent,
                                    "Загрузка… "
                                        + (received / 1048576L)
                                        + " из "
                                        + (total / 1048576L)
                                        + " МБ"
                                );
                            }
                            else
                            {
                                Report(
                                    0,
                                    "Загрузка… " + (received / 1048576L) + " МБ"
                                );
                            }
                        }
                    }
                }
            }
            if (File.Exists(destination))
            {
                File.Delete(destination);
            }
            File.Move(partPath, destination);
            Report(850, "Загрузка завершена");
        }

        private static bool HashMatches(string path, string expected)
        {
            if (String.IsNullOrEmpty(expected) || !File.Exists(path))
            {
                return false;
            }
            using (SHA256 sha = SHA256.Create())
            using (FileStream stream = File.OpenRead(path))
            {
                string actual = BitConverter
                    .ToString(sha.ComputeHash(stream))
                    .Replace("-", "")
                    .ToLowerInvariant();
                return String.Equals(actual, expected.Trim().ToLowerInvariant(), StringComparison.Ordinal);
            }
        }

        private static void MoveOrCopyDirectory(string source, string target)
        {
            try
            {
                Directory.Move(source, target);
                return;
            }
            catch (IOException)
            {
                // Между разными дисками Directory.Move не работает.
            }
            CopyDirectory(source, target);
            Directory.Delete(source, true);
        }

        private static void CopyDirectory(string source, string target)
        {
            Directory.CreateDirectory(target);
            foreach (string file in Directory.GetFiles(source))
            {
                File.Copy(file, Path.Combine(target, Path.GetFileName(file)), true);
            }
            foreach (string directory in Directory.GetDirectories(source))
            {
                CopyDirectory(
                    directory,
                    Path.Combine(target, Path.GetFileName(directory))
                );
            }
        }

        private static void TryDeleteDirectory(string path)
        {
            try
            {
                if (Directory.Exists(path))
                {
                    Directory.Delete(path, true);
                }
            }
            catch
            {
                // Временный каталог не критичен.
            }
        }

        private void OnFormClosing(object sender, FormClosingEventArgs e)
        {
            if (_downloading && _cancellation != null)
            {
                _cancellation.Cancel();
            }
        }
    }
}
