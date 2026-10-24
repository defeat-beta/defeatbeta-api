"""Select a dataset endpoint without replacing either product's HTTP stack."""

from contextlib import contextmanager
from unittest.mock import patch


@contextmanager
def dataset_endpoint(endpoint=None):
    if endpoint is None:
        yield
        return
    from defeatbeta_api.client.hugging_face_client import HuggingFaceClient

    original_request = HuggingFaceClient._make_request
    original_resolve = HuggingFaceClient.resolve_cdn_info

    def metadata(self, url):
        return original_request(self, endpoint + "/spec.json")

    def resolve(self, url, *args, **kwargs):
        return original_resolve(self, endpoint + "/resolve/" + url.rsplit("/", 1)[-1], *args, **kwargs)

    with patch.object(HuggingFaceClient, "_make_request", metadata), \
            patch.object(HuggingFaceClient, "resolve_cdn_info", resolve):
        yield
