import FreeCAD
import pytest


@pytest.fixture(autouse=True)
def close_documents_after_test():
    yield
    for document in FreeCAD.listDocuments().keys():
        FreeCAD.closeDocument(document)
