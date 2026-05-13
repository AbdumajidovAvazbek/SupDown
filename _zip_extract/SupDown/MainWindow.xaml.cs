using System.IO;
using System.Net.Http;
using System.Text;
using System.Windows;
using System.Windows.Forms;
using YoutubeExplode;
using YoutubeExplode.Videos.ClosedCaptions;

namespace SupDown;

public partial class MainWindow : Window
{
    private string? _plainText;

    public MainWindow()
    {
        InitializeComponent();
    }

    private void BrowseFolder_Click(object sender, RoutedEventArgs e)
    {
        using var dialog = new FolderBrowserDialog
        {
            Description = "Subtitllar saqlanadigan papkani tanlang",
            UseDescriptionForTitle = true
        };
        if (dialog.ShowDialog() == System.Windows.Forms.DialogResult.OK)
            FolderTextBox.Text = dialog.SelectedPath;
    }

    private void BrowseCookies_Click(object sender, RoutedEventArgs e)
    {
        using var dialog = new OpenFileDialog
        {
            Title = "cookies.txt faylini tanlang",
            Filter = "Text files (*.txt)|*.txt|All files (*.*)|*.*",
            FilterIndex = 1
        };
        if (dialog.ShowDialog() == System.Windows.Forms.DialogResult.OK)
            CookiesTextBox.Text = dialog.FileName;
    }

    private async void Download_Click(object sender, RoutedEventArgs e)
    {
        var url = UrlTextBox.Text.Trim();
        var folder = FolderTextBox.Text.Trim();
        var lang = LangTextBox.Text.Trim().ToLowerInvariant();
        var cookiesFile = CookiesTextBox.Text.Trim();

        if (string.IsNullOrEmpty(url))  { Log("Xato: YouTube havola kiritilmagan."); return; }
        if (string.IsNullOrEmpty(folder)) { Log("Xato: Saqlash papkasi tanlanmagan."); return; }
        if (!Directory.Exists(folder))  { Log("Xato: Tanlangan papka mavjud emas."); return; }

        DownloadBtn.IsEnabled = false;
        LogBox.Text = string.Empty;

        try
        {
            var youtube = BuildClient(cookiesFile);

            Log("Video ma'lumotlari yuklanmoqda...");
            var video = await youtube.Videos.GetAsync(url);
            Log($"Video topildi: {video.Title}");

            Log("Subtitl ro'yxati olinmoqda...");
            var manifest = await youtube.Videos.ClosedCaptions.GetManifestAsync(url);
            var tracks = manifest.Tracks;

            if (!tracks.Any())
            {
                Log("Xato: Bu videoda subtitl mavjud emas.");
                return;
            }

            ClosedCaptionTrackInfo? chosen;
            if (!string.IsNullOrEmpty(lang))
            {
                chosen = tracks.FirstOrDefault(t =>
                    t.Language.Code.StartsWith(lang, StringComparison.OrdinalIgnoreCase));

                if (chosen is null)
                {
                    Log($"'{lang}' tili topilmadi. Mavjud tillar:");
                    foreach (var t in tracks)
                        Log($"  • {t.Language.Code} — {t.Language.Name}");
                    return;
                }
            }
            else
            {
                chosen = tracks[0];
                Log($"Til tanlanmadi — birinchi topilgan: {chosen.Language.Code} ({chosen.Language.Name})");
            }

            Log($"Subtitl yuklanmoqda: {chosen.Language.Code} ({chosen.Language.Name})...");
            var track = await youtube.Videos.ClosedCaptions.GetAsync(chosen);

            var safeTitle = SanitizeFileName(video.Title);
            var filePath = Path.Combine(folder, $"{safeTitle}.txt");

            _plainText = BuildPlainText(track);
            CopyBtn.IsEnabled = true;

            Log("TXT fayl yozilmoqda...");
            await File.WriteAllTextAsync(filePath, _plainText,
                new UTF8Encoding(encoderShouldEmitUTF8Identifier: true));

            Log($"Muvaffaqiyatli saqlandi:");
            Log($"  {filePath}");
        }
        catch (Exception ex)
        {
            Log($"Xato: {ex.Message}");
        }
        finally
        {
            DownloadBtn.IsEnabled = true;
        }
    }

    private void CopyText_Click(object sender, RoutedEventArgs e)
    {
        if (string.IsNullOrEmpty(_plainText)) return;
        System.Windows.Clipboard.SetText(_plainText);
        Log("Matn clipboard ga nusxalandi. Claude.ai ga yapishtirishingiz mumkin.");
    }

    private static string BuildPlainText(ClosedCaptionTrack track) =>
        string.Join(" ", track.Captions.Select(c => c.Text).Where(t => !string.IsNullOrWhiteSpace(t)));

    private YoutubeClient BuildClient(string cookiesFilePath)
    {
        if (string.IsNullOrEmpty(cookiesFilePath) || !File.Exists(cookiesFilePath))
            return new YoutubeClient();

        var cookieHeader = BuildCookieHeader(cookiesFilePath);
        if (string.IsNullOrEmpty(cookieHeader))
            return new YoutubeClient();

        var httpClient = new HttpClient(new CookieInjectingHandler(cookieHeader));
        Log($"Cookies yuklandi.");
        return new YoutubeClient(httpClient);
    }

    private static string BuildCookieHeader(string path)
    {
        var pairs = new List<string>();
        foreach (var line in File.ReadLines(path))
        {
            if (string.IsNullOrWhiteSpace(line) || line.StartsWith('#')) continue;
            var parts = line.Split('\t');
            if (parts.Length < 7) continue;
            var name  = parts[5].Trim();
            var value = parts[6].Trim();
            if (!string.IsNullOrEmpty(name))
                pairs.Add($"{name}={value}");
        }
        return string.Join("; ", pairs);
    }

    private sealed class CookieInjectingHandler(string cookieHeader) : DelegatingHandler(new HttpClientHandler())
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            request.Headers.TryAddWithoutValidation("Cookie", cookieHeader);
            return base.SendAsync(request, cancellationToken);
        }
    }

    private static string BuildSrt(ClosedCaptionTrack track)
    {
        var sb = new StringBuilder();
        int i = 1;
        foreach (var c in track.Captions)
        {
            sb.AppendLine(i++.ToString());
            sb.AppendLine($"{Ts(c.Offset)} --> {Ts(c.Offset + c.Duration)}");
            sb.AppendLine(c.Text);
            sb.AppendLine();
        }
        return sb.ToString();
    }

    private static string Ts(TimeSpan t) =>
        $"{(int)t.TotalHours:D2}:{t.Minutes:D2}:{t.Seconds:D2},{t.Milliseconds:D3}";

    private static string SanitizeFileName(string name)
    {
        var invalid = Path.GetInvalidFileNameChars();
        var safe = new string(name.Select(c => invalid.Contains(c) ? '_' : c).ToArray());
        return safe.Length > 100 ? safe[..100] : safe;
    }

    private void Log(string message)
    {
        LogBox.AppendText(message + Environment.NewLine);
        LogScroll.ScrollToBottom();
    }
}
