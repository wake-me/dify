from core.extension.api_based_extension_requestor import APIBasedExtensionRequestor
from core.helper.encrypter import decrypt_token, encrypt_token
from extensions.ext_database import db
from models.api_based_extension import APIBasedExtension, APIBasedExtensionPoint


class APIBasedExtensionService:
    @staticmethod
    def get_all_by_tenant_id(tenant_id: str) -> list[APIBasedExtension]:
        extension_list = (
            db.session.query(APIBasedExtension)
            .filter_by(tenant_id=tenant_id)
            .order_by(APIBasedExtension.created_at.desc())
            .all()
        )

        # 对查询结果中的每个扩展的API密钥进行解密
        for extension in extension_list:
            extension.api_key = decrypt_token(extension.tenant_id, extension.api_key)

        return extension_list

    @classmethod
    def save(cls, extension_data: APIBasedExtension) -> APIBasedExtension:
        """
        保存扩展数据到数据库。
        
        参数:
        - cls: 类的引用，用于调用类方法或属性。
        - extension_data: APIBasedExtension 类型，包含要保存的扩展数据。
        
        返回值:
        - 经过处理（如API密钥加密）后的扩展数据对象。
        """
        # 验证扩展数据的有效性
        cls._validation(extension_data)

        # 使用tenant_id和api_key生成加密的api_key
        extension_data.api_key = encrypt_token(extension_data.tenant_id, extension_data.api_key)

        # 将扩展数据对象添加到数据库会话并提交，实现持久化
        db.session.add(extension_data)
        db.session.commit()
        
        # 返回处理后的扩展数据对象
        return extension_data

    @staticmethod
    def delete(extension_data: APIBasedExtension) -> None:
        """
        从数据库中删除指定的扩展数据。
        
        参数:
        extension_data - APIBasedExtension 类型，表示待删除的扩展数据。
        
        返回值:
        无
        """
        db.session.delete(extension_data)  # 从数据库会话中删除指定的扩展数据对象
        db.session.commit()  # 提交数据库会话，执行删除操作

    @staticmethod
    def get_with_tenant_id(tenant_id: str, api_based_extension_id: str) -> APIBasedExtension:
        extension = (
            db.session.query(APIBasedExtension)
            .filter_by(tenant_id=tenant_id)
            .filter_by(id=api_based_extension_id)
            .first()
        )

        # 如果查询结果为空，则抛出未找到异常
        if not extension:
            raise ValueError("API based extension is not found")

        # 对查询到的API扩展的API密钥进行解密
        extension.api_key = decrypt_token(extension.tenant_id, extension.api_key)

        return extension

    @classmethod
    def _validation(cls, extension_data: APIBasedExtension) -> None:
        """
        对扩展数据进行验证。

        参数:
        - cls: 类的引用，用于可能的类方法调用。
        - extension_data: APIBasedExtension 类的实例，包含需要验证的扩展数据。

        返回值:
        - 无。若验证失败，将抛出 ValueError。

        验证规则包括：
        - 名称（name）不能为空，并且必须唯一。
        - API 端点（api_endpoint）不能为空。
        - API 密钥（api_key）不能为空，且长度至少为 5 个字符。
        - 检查 API 端点的连通性。
        """

        # 验证 name 字段
        if not extension_data.name:
            raise ValueError("name must not be empty")

        if not extension_data.id:
            # case one: check new data, name must be unique
            is_name_existed = (
                db.session.query(APIBasedExtension)
                .filter_by(tenant_id=extension_data.tenant_id)
                .filter_by(name=extension_data.name)
                .first()
            )

            if is_name_existed:
                raise ValueError("name must be unique, it is already existed")
        else:
            # case two: check existing data, name must be unique
            is_name_existed = (
                db.session.query(APIBasedExtension)
                .filter_by(tenant_id=extension_data.tenant_id)
                .filter_by(name=extension_data.name)
                .filter(APIBasedExtension.id != extension_data.id)
                .first()
            )

            if is_name_existed:
                raise ValueError("name must be unique, it is already existed")

        # 验证 api_endpoint 字段
        if not extension_data.api_endpoint:
            raise ValueError("api_endpoint must not be empty")

        # 验证 api_key 字段
        if not extension_data.api_key:
            raise ValueError("api_key must not be empty")

        if len(extension_data.api_key) < 5:
            raise ValueError("api_key must be at least 5 characters")

        # 检查 API 端点的连通性
        cls._ping_connection(extension_data)

    @staticmethod
    def _ping_connection(extension_data: APIBasedExtension) -> None:
        """
        尝试通过发送一个PING请求来检验与扩展的连接是否正常。
        
        :param extension_data: 一个包含API端点和API密钥信息的APIBasedExtension对象，用于建立请求。
        :return: 无返回值。
        """
        try:
            # 使用提供的API端点和密钥创建一个APIBasedExtensionRequestor实例
            client = APIBasedExtensionRequestor(extension_data.api_endpoint, extension_data.api_key)
            # 向API发送PING请求
            resp = client.request(point=APIBasedExtensionPoint.PING, params={})
            if resp.get("result") != "pong":
                raise ValueError(resp)
        except Exception as e:
            # 如果在尝试连接过程中遇到任何异常，则抛出一个包含连接错误信息的ValueError异常
            raise ValueError("connection error: {}".format(e))
