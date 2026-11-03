

def entry_id_from_path(path):
    raise NotImplementedError('not implemented: entry_id_from_path')


def receipt_dir(root):
    raise NotImplementedError('not implemented: receipt_dir')


def receipt_post(db, root, entry_id, content_type, body):
    raise NotImplementedError('not implemented: receipt_post')


def receipt_get(db, root, entry_id):
    raise NotImplementedError('not implemented: receipt_get')
