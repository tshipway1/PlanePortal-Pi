import os


PHOTO_CACHE_PATH = "/planeportal_photo.bmp"


class PhotoManager:
    def __init__(self, config, session_provider):
        self._config = config
        self._session_provider = session_provider
        self._attempted_url = None
        self._photo_path = None

    def ensure_test_photo(self):
        if not self._config.enable_photos:
            return None, None

        image_url = self._config.test_image_url
        if not image_url:
            return None, None

        if self._attempted_url == image_url:
            if self._photo_path:
                return self._photo_path, "photo ready"
            return None, "photo fallback"

        self._attempted_url = image_url
        self._photo_path = None

        self._delete_cache_file()
        self._download_bitmap(image_url)
        self._validate_bitmap()
        self._photo_path = PHOTO_CACHE_PATH
        return self._photo_path, "photo ready"

    def _download_bitmap(self, image_url):
        response = self._session_provider().get(
            image_url,
            headers={"Accept": "image/bmp,*/*"},
            stream=True,
        )
        try:
            if response.status_code >= 400:
                raise RuntimeError("Photo request failed: {}".format(response.status_code))

            with open(PHOTO_CACHE_PATH, "wb") as bitmap_file:
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        bitmap_file.write(chunk)
        finally:
            response.close()

    def _validate_bitmap(self):
        with open(PHOTO_CACHE_PATH, "rb") as bitmap_file:
            signature = bitmap_file.read(2)
        if signature != b"BM":
            self._delete_cache_file()
            raise RuntimeError("Photo URL must return a BMP image")

    def _delete_cache_file(self):
        try:
            os.remove(PHOTO_CACHE_PATH)
        except OSError:
            pass