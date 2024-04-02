
class InfiniteScrollPagination:
    """
    无限滚动分页类。
    
    参数:
    - data: 分页数据列表。
    - limit: 每页显示的数据条数。
    - has_more: 是否还有更多数据可供加载的布尔值。
    """

    def __init__(self, data, limit, has_more):
        """
        初始化无限滚动分页对象。
        
        参数:
        - data: 分页数据列表。
        - limit: 每页显示的数据条数。
        - has_more: 是否还有更多数据可供加载的布尔值。
        """
        self.data = data  # 分页数据
        self.limit = limit  # 每页数据的限制数量
        self.has_more = has_more  # 标记是否还有更多的数据页