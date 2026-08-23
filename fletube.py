import flet as ft
import yt_dlp
import flet_video as ftv
import asyncio
import os
import tempfile
import imageio_ffmpeg
import threading

FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
COOKIES_PATH = os.path.join(os.path.dirname(__file__), 'youtube_cookies.txt')

def get_video_info(url):
    ydl_opts = {
        'quiet': True,       # suppress console spam
        'skip_download': True,  # don't actually download, just fetch metadata
    }
    with yt_dlp.YoutubeDL(params=ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return info

def search_youtube(query, max_results=10):
    ydl_opts = {'quiet': True, 'extract_flat': True}  # extract_flat = don't resolve full info per result, just get basic list (fast)
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        search_query = f"ytsearch{max_results}:{query}"
        result = ydl.extract_info(search_query, download=False)
        return result['entries']  # list of video dicts (id, title, url, etc.)

current_downloaded_id = None
DOWNLOAD_DIR = os.path.join(tempfile.gettempdir(), "flettube_cache")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
downloaded_ids: set[str] = set()
#bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best

def download_video(video_id: str, on_progress=None) -> str:
    output_template = os.path.join(DOWNLOAD_DIR, f"{video_id}.%(ext)s")

    def progress_hook(d):
        if on_progress is None:
            return

        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate')
            downloaded = d.get('downloaded_bytes', 0)
            percent = (downloaded / total * 100) if total else 0
            speed = d.get('speed')  # bytes/sec, có thể là None
            eta = d.get('eta')      # giây còn lại, có thể là None

            on_progress({
                'status': 'downloading',
                'percent': percent,
                'speed': speed,
                'eta': eta,
            })

        elif d['status'] == 'finished':
            on_progress({'status': 'merging'})  # ffmpeg đang ghép Video+Audio

    ydl_opts = {
        'quiet': False,
        'verbose': True,
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': output_template,
        'merge_output_format': 'mp4',
        'ffmpeg_location': FFMPEG_PATH,
        'progress_hooks': [progress_hook],
        'cookiesfrombrowser': None,
        'cookies': COOKIES_PATH,
        'extractor_args': {
            'youtube': {
                'player_client': ['web'],
            }
        },
    }

    url = f"https://www.youtube.com/watch?v={video_id}"
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    downloaded_ids.add(video_id)

    final_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp4")
    if os.path.exists(final_path):
        if on_progress:
            on_progress({'status': 'done'})
        return final_path

    for filename in os.listdir(DOWNLOAD_DIR):
        if filename.startswith(video_id):
            if on_progress:
                on_progress({'status': 'done'})
            return os.path.join(DOWNLOAD_DIR, filename)

    raise RuntimeError(f"Download finished but file not found for {video_id}.")


def delete_downloaded_video(video_id: str):
    """Xóa File Video đã tải (gọi khi quay lại trang Search)."""
    for filename in os.listdir(DOWNLOAD_DIR):
        if filename.startswith(video_id):
            try:
                os.remove(os.path.join(DOWNLOAD_DIR, filename))
            except OSError as ex:
                print(f"Failed to delete {filename}: {ex}")

def get_stream_url(video_id: str) -> str:
    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        'quiet': True,
        'format': 'best',
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

        # Đôi khi kết quả trả về dạng Playlist (VD: 1 phần tử) thay vì Video đơn lẻ
        if info is None:
            raise RuntimeError("Could not extract video info.")
        if 'entries' in info and info['entries']:
            info = info['entries'][0]

        # Trường hợp bình thường: có URL trực tiếp ở top-level
        if info.get('url'):
            return info['url']

        # Trường hợp Format được chọn là ghép nhiều luồng (video+audio riêng)
        if info.get('requested_formats'):
            for fmt in info['requested_formats']:
                if fmt.get('url'):
                    return fmt['url']

        # Fallback cuối: tự tìm trong danh sách toàn bộ Format có sẵn
        formats = info.get('formats', [])
        for fmt in reversed(formats):  # yt-dlp thường sắp xếp từ thấp -> cao chất lượng
            if fmt.get('acodec') != 'none' and fmt.get('vcodec') != 'none' and fmt.get('url'):
                return fmt['url']

        raise RuntimeError(f"No playable stream URL found for video {video_id}.")

def get_video_details(video_id: str) -> dict:
    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {'quiet': True, 'skip_download': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return {
            'view_count': info.get('view_count'),
            'like_count': info.get('like_count'),
            'duration': info.get('duration'),
            'upload_date': info.get('upload_date'),
        }

def main(page: ft.Page):
    page.title = "FleTube"
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.horizontal_alignment = ft.CrossAxisAlignment.START

    tf1 = ft.TextField(multiline=False, label="Search", expand=True)
    results_list = ft.ListView(expand=True, spacing=5, padding=10)

    async def window_event(e: ft.WindowEvent):
        if e.type == ft.WindowEventType.CLOSE:
            cleanup_all_downloads()
            await page.window.destroy()

    page.window.prevent_close = True
    page.window.on_event = window_event

    def cleanup_all_downloads():
        for video_id in list(downloaded_ids):
            delete_downloaded_video(video_id)
        downloaded_ids.clear()

    def video_clicked(video_id: str, title: str):
        async def handler(e: ft.Event):
            await page.push_route(f"/watch/{video_id}?title={title}")
        return handler

    async def button_search_clicked(e: ft.Event):
        query = tf1.value
        if not query:
            return

        results_list.controls.clear()
        results_list.controls.append(ft.ProgressRing())
        page.update()

        results = search_youtube(query)

        results_list.controls.clear()

        if not results:
            results_list.controls.append(ft.Text("No results found."))
        else:
            for video in results:
                title = video.get('title', 'Untitled')
                video_id = video.get('id', '')

                results_list.controls.append(
                    ft.ListTile(
                        title=ft.Text(title),
                        subtitle=ft.Text(video.get('uploader', '')),
                        leading=ft.Icon(ft.Icons.PLAY_CIRCLE_OUTLINE),
                        on_click=video_clicked(video_id, title),
                    )
                )

        page.update()

    tf1.on_submit = button_search_clicked

    def build_search_view():
        return ft.View(
            route="/",
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.CENTER,
                    controls=[
                        tf1,
                        ft.IconButton(
                            icon=ft.Icons.ARROW_RIGHT,
                            icon_color=ft.Colors.BLUE_300,
                            on_click=button_search_clicked,
                        ),
                    ],
                ),
                results_list,
            ],
        )

    def format_view_count(count):
        if count is None:
            return "N/A views"
        if count >= 1_000_000_000:
            return f"{count / 1_000_000_000:.1f}B views"
        if count >= 1_000_000:
            return f"{count / 1_000_000:.1f}M views"
        if count >= 1_000:
            return f"{count / 1_000:.1f}K views"
        return f"{count} views"


    def format_upload_date(date_str):
        if not date_str or len(date_str) != 8:
            return "Unknown date"
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"  # YYYYMMDD -> YYYY-MM-DD


    def build_watch_view(video_id: str, title: str):
        async def go_back(e):
            await page.push_route("/")

        content_container = ft.Container(
            content=ft.Text("Loading..."),
            expand=True,
            alignment=ft.Alignment.CENTER,
        )

        views_text = ft.Text("Loading info...")
        likes_text = ft.Text("")
        upload_text = ft.Text("")

        info_container = ft.Container(
            content=ft.Column(
                controls=[ft.Row(
                controls=[
                    views_text,
                    ft.Text(" • "),
                    likes_text,
                ],
            ), upload_text],
            ),
            alignment=ft.Alignment.CENTER_LEFT,
            padding=10,
        )

        view = ft.View(
            route=f"/watch/{video_id}",
            controls=[
                ft.AppBar(
                    title=ft.Text(title),
                    leading=ft.IconButton(icon=ft.Icons.ARROW_BACK, on_click=go_back),
                ),
                content_container,
                info_container,
            ],
        )

        def on_progress(info):
            status = info['status']

            if status == 'downloading':
                percent = info['percent']
                page.title = f"FleTube — Downloading {percent:.0f}%..."
            elif status == 'merging':
                page.title = "FleTube — Processing..."
            elif status == 'done':
                page.title = "FleTube"

            page.update()

        def do_download():
            try:
                local_path = download_video(video_id, on_progress=on_progress)
                content_container.content = ftv.Video(
                    playlist=[ftv.VideoMedia(local_path)],
                    autoplay=True,
                    expand=True,
                )
            except Exception as ex:
                content_container.content = ft.Text(f"Error: {ex}")
                page.title = "FleTube — Error"
            page.update()

        def do_fetch_details():
            try:
                details = get_video_details(video_id)
                views_text.value = format_view_count(details.get('view_count'))
                likes_text.value = format_view_count(details.get('like_count')).replace("views", "likes")
                upload_text.value = f"Uploaded in {format_upload_date(details.get('upload_date'))}"
            except Exception as ex:
                views_text.value = f"Could not load video info: {ex}"
            page.update()

        threading.Thread(target=do_download, daemon=True).start()
        threading.Thread(target=do_fetch_details, daemon=True).start()

        return view

    def route_change(e=None):
        page.views.clear()
        page.views.append(build_search_view())

        if page.route.startswith("/watch/"):
            route_parts = page.route.split("?")
            path = route_parts[0]
            video_id = path.replace("/watch/", "")

            title = "Now Playing"
            if len(route_parts) > 1 and "title=" in route_parts[1]:
                title = route_parts[1].split("title=")[1]

            page.views.append(build_watch_view(video_id, title))

        page.update()

    async def view_pop(e: ft.ViewPopEvent):
        if e.view is not None:
            page.views.remove(e.view)
            top_view = page.views[-1]
            await page.push_route(top_view.route)

    page.on_route_change = route_change
    page.on_view_pop = view_pop
    route_change()  # render the initial view directly, no need to push_route on startup

ft.run(main)