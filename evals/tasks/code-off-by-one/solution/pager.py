def paginate(items, page, per_page):
    """Trả về các phần tử của trang `page`, đánh số từ 1."""
    start = (page - 1) * per_page
    return items[start:start + per_page]
