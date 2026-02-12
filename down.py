import yt_dlp

def download_video(url: str, output_path: str = "."):
    ydl_opts = {
        "outtmpl": f"{output_path}/%(title)s.%(ext)s",
        "format": "bestvideo+bestaudio/best"
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

if __name__ == "__main__":
    video_url = input("Enter YouTube URL: ")
    download_video(video_url)
