'''
Author: fanwenqi hi.fanwenqi@gmail.com
Date: 2024-04-01 16:39:26
LastEditors: fanwenqi hi.fanwenqi@gmail.com
LastEditTime: 2024-04-02 10:44:58
FilePath: /dify/api/models/source.py
Description: 这是默认设置,请设置`customMade`, 打开koroFileHeader查看配置 进行设置: https://github.com/OBKoro1/koro1FileHeader/wiki/%E9%85%8D%E7%BD%AE
'''
from sqlalchemy.dialects.postgresql import JSONB, UUID

from extensions.ext_database import db


class DataSourceBinding(db.Model):
    """
    数据源绑定类，用于表示数据源与用户之间的绑定关系。
    
    属性:
    - id: 绑定关系的唯一标识符，使用UUID作为类型。
    - tenant_id: 租户的唯一标识符，不可为空。
    - access_token: 访问数据源所需的令牌，不可为空。
    - provider: 数据源的提供者，不可为空。
    - source_info: 关于数据源的详细信息，以JSONB格式存储，不可为空。
    - created_at: 绑定关系创建的时间，不可为空，默认为当前时间。
    - updated_at: 绑定关系最后更新的时间，不可为空，默认为当前时间。
    - disabled: 是否禁用该绑定关系，可为空，默认为false。
    
    表结构:
    - 主键约束由'id'字段组成。
    - 索引包括基于'tenant_id'的索引和基于'source_info'的GIN索引。
    """
    
    __tablename__ = 'data_source_bindings'  # 指定数据库表名为data_source_bindings
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='source_binding_pkey'),  # 主键约束
        db.Index('source_binding_tenant_id_idx', 'tenant_id'),  # 基于tenant_id的索引
        db.Index('source_info_idx', "source_info", postgresql_using='gin')  # 基于source_info的GIN索引
    )

    id = db.Column(UUID, server_default=db.text('uuid_generate_v4()'))  # 绑定关系的唯一标识符
    tenant_id = db.Column(UUID, nullable=False)  # 租户的唯一标识符
    access_token = db.Column(db.String(255), nullable=False)  # 访问令牌
    provider = db.Column(db.String(255), nullable=False)  # 提供者
    source_info = db.Column(JSONB, nullable=False)  # 数据源信息
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))  # 创建时间
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))  # 更新时间
    disabled = db.Column(db.Boolean, nullable=True, server_default=db.text('false'))  # 是否禁用