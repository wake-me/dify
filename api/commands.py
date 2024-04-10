import base64
import json
import secrets

import click
from flask import current_app
from werkzeug.exceptions import NotFound

from core.rag.datasource.vdb.vector_factory import Vector
from core.rag.models.document import Document
from extensions.ext_database import db
from libs.helper import email as email_validate
from libs.password import hash_password, password_pattern, valid_password
from libs.rsa import generate_key_pair
from models.account import Tenant
from models.dataset import Dataset, DatasetCollectionBinding, DocumentSegment
from models.dataset import Document as DatasetDocument
from models.model import Account, App, AppAnnotationSetting, AppMode, Conversation, MessageAnnotation
from models.provider import Provider, ProviderModel


@click.command('reset-password', help='Reset the account password.')
@click.option('--email', prompt=True, help='The email address of the account whose password you need to reset')
@click.option('--new-password', prompt=True, help='the new password.')
@click.option('--password-confirm', prompt=True, help='the new password confirm.')
def reset_password(email, new_password, password_confirm):
    """
    重置账号密码
    仅在SELF_HOSTED模式下可用
    参数:
    - email: 需要重置密码的账号的电子邮件地址
    - new_password: 新密码
    - password_confirm: 确认新密码
    """
    # 验证新密码和确认密码是否匹配
    if str(new_password).strip() != str(password_confirm).strip():
        click.echo(click.style('sorry. The two passwords do not match.', fg='red'))
        return

    # 查询指定电子邮件地址的账号
    account = db.session.query(Account). \
        filter(Account.email == email). \
        one_or_none()

    # 账号不存在时的处理
    if not account:
        click.echo(click.style('sorry. the account: [{}] not exist .'.format(email), fg='red'))
        return

    # 验证新密码是否符合要求
    try:
        valid_password(new_password)
    except:
        click.echo(
            click.style('sorry. The passwords must match {} '.format(password_pattern), fg='red'))
        return

    # 生成密码盐并加密密码
    salt = secrets.token_bytes(16)
    base64_salt = base64.b64encode(salt).decode()

    password_hashed = hash_password(new_password, salt)
    base64_password_hashed = base64.b64encode(password_hashed).decode()
    account.password = base64_password_hashed
    account.password_salt = base64_salt
    db.session.commit()
    click.echo(click.style('Congratulations!, password has been reset.', fg='green'))


@click.command('reset-email', help='Reset the account email.')
@click.option('--email', prompt=True, help='The old email address of the account whose email you need to reset')
@click.option('--new-email', prompt=True, help='the new email.')
@click.option('--email-confirm', prompt=True, help='the new email confirm.')
def reset_email(email, new_email, email_confirm):
    """
    替换账号电子邮件地址
    参数:
    - email: 需要替换的旧电子邮件地址
    - new_email: 新电子邮件地址
    - email_confirm: 确认新电子邮件地址
    """
    # 验证新电子邮件和确认电子邮件是否匹配
    if str(new_email).strip() != str(email_confirm).strip():
        click.echo(click.style('Sorry, new email and confirm email do not match.', fg='red'))
        return

    # 查询指定电子邮件地址的账号
    account = db.session.query(Account). \
        filter(Account.email == email). \
        one_or_none()

    # 账号不存在时的处理
    if not account:
        click.echo(click.style('sorry. the account: [{}] not exist .'.format(email), fg='red'))
        return

    # 验证新电子邮件地址的有效性
    try:
        email_validate(new_email)
    except:
        click.echo(
            click.style('sorry. {} is not a valid email. '.format(email), fg='red'))
        return

    account.email = new_email
    db.session.commit()
    click.echo(click.style('Congratulations!, email has been reset.', fg='green'))


@click.command('reset-encrypt-key-pair', help='Reset the asymmetric key pair of workspace for encrypt LLM credentials. '
                                              'After the reset, all LLM credentials will become invalid, '
                                              'requiring re-entry.'
                                              'Only support SELF_HOSTED mode.')
@click.confirmation_option(prompt=click.style('Are you sure you want to reset encrypt key pair?'
                                              ' this operation cannot be rolled back!', fg='red'))
def reset_encrypt_key_pair():
    """
    重置工作空间的加密密钥对，用于加密LLM凭据。
    重置后，所有LLM凭据将变得无效，需要重新输入。
    仅支持SELF_HOSTED模式。
    """
    # 检查当前应用版本是否为SELF_HOSTED，如果不是，则报错并退出
    if current_app.config['EDITION'] != 'SELF_HOSTED':
        click.echo(click.style('Sorry, only support SELF_HOSTED mode.', fg='red'))
        return

    # 从数据库中查询所有租户信息
    tenants = db.session.query(Tenant).all()
    for tenant in tenants:
        # 如果没有找到租户信息，则报错并退出
        if not tenant:
            click.echo(click.style('Sorry, no workspace found. Please enter /install to initialize.', fg='red'))
            return

        # 为当前租户生成新的密钥对
        tenant.encrypt_public_key = generate_key_pair(tenant.id)

        # 删除当前租户的所有自定义提供商和模型提供者信息
        db.session.query(Provider).filter(Provider.provider_type == 'custom', Provider.tenant_id == tenant.id).delete()
        db.session.query(ProviderModel).filter(ProviderModel.tenant_id == tenant.id).delete()
        db.session.commit()

        # 提示密钥对重置成功
        click.echo(click.style('Congratulations! '
                               'the asymmetric key pair of workspace {} has been reset.'.format(tenant.id), fg='green'))


@click.command('vdb-migrate', help='migrate vector db.')
@click.option('--scope', default='all', prompt=False, help='The scope of vector database to migrate, Default is All.')
def vdb_migrate(scope: str):
    """
    根据指定的范围执行数据库迁移。
    
    参数:
    scope: 字符串，指定迁移的范围，可以是'knowledge'、'annotation'或'all'。
    
    返回值:
    无返回值。
    """
    # 根据范围决定是否迁移知识向量数据库
    if scope in ['knowledge', 'all']:
        migrate_knowledge_vector_database()
    # 根据范围决定是否迁移注释向量数据库
    if scope in ['annotation', 'all']:
        migrate_annotation_vector_database()


def migrate_annotation_vector_database():
    """
    迁移注解数据到目标向量数据库。
    此函数遍历所有状态为正常的app，为每个app的注解数据创建向量索引。如果app没有启用注解设置或者相应的集合绑定不存在，则跳过该app。
    对于每个启用注解的app，它会删除旧的向量索引（如果存在），然后创建一个新的向量索引，包含所有的注解文档。

    参数:
    无

    返回值:
    无
    """
    # 开始迁移注解数据
    click.echo(click.style('Start migrate annotation data.', fg='green'))
    create_count = 0  # 成功创建索引的app数量
    skipped_count = 0  # 被跳过的app数量
    total_count = 0  # 处理的app总数量
    page = 1  # 分页查询的起始页码

    while True:
        try:
            # 查询状态为正常的app信息
            apps = db.session.query(App).filter(
                App.status == 'normal'
            ).order_by(App.created_at.desc()).paginate(page=page, per_page=50)
        except NotFound:
            break  # 未找到app时结束循环

        page += 1  # 更新页码以获取下一页app信息
        for app in apps:
            total_count += 1  # 更新处理的app总数量
            # 处理单个app的注解数据
            click.echo(f'Processing the {total_count} app {app.id}. '
                       + f'{create_count} created, {skipped_count} skipped.')
            try:
                # 尝试创建app的注解索引
                click.echo('Create app annotation index: {}'.format(app.id))
                app_annotation_setting = db.session.query(AppAnnotationSetting).filter(
                    AppAnnotationSetting.app_id == app.id
                ).first()

                if not app_annotation_setting:
                    skipped_count += 1  # 如果app没有启用注解设置，则跳过
                    click.echo('App annotation setting is disabled: {}'.format(app.id))
                    continue

                # 获取集合绑定信息
                dataset_collection_binding = db.session.query(DatasetCollectionBinding).filter(
                    DatasetCollectionBinding.id == app_annotation_setting.collection_binding_id
                ).first()
                if not dataset_collection_binding:
                    click.echo('App annotation collection binding is not exist: {}'.format(app.id))
                    continue

                # 查询app的注解信息
                annotations = db.session.query(MessageAnnotation).filter(MessageAnnotation.app_id == app.id).all()
                # 创建Dataset对象
                dataset = Dataset(
                    id=app.id,
                    tenant_id=app.tenant_id,
                    indexing_technique='high_quality',
                    embedding_model_provider=dataset_collection_binding.provider_name,
                    embedding_model=dataset_collection_binding.model_name,
                    collection_binding_id=dataset_collection_binding.id
                )
                documents = []
                # 如果有注解数据，则创建文档对象
                if annotations:
                    for annotation in annotations:
                        document = Document(
                            page_content=annotation.question,
                            metadata={
                                "annotation_id": annotation.id,
                                "app_id": app.id,
                                "doc_id": annotation.id
                            }
                        )
                        documents.append(document)

                # 创建向量对象
                vector = Vector(dataset, attributes=['doc_id', 'annotation_id', 'app_id'])
                click.echo(f"Start to migrate annotation, app_id: {app.id}.")

                try:
                    vector.delete()  # 尝试删除旧的索引
                    click.echo(
                        click.style(f'Successfully delete vector index for app: {app.id}.',
                                    fg='green'))
                except Exception as e:
                    click.echo(
                        click.style(f'Failed to delete vector index for app {app.id}.',
                                    fg='red'))
                    raise e

                if documents:
                    try:
                        # 创建新的向量索引
                        click.echo(click.style(
                            f'Start to created vector index with {len(documents)} annotations for app {app.id}.',
                            fg='green'))
                        vector.create(documents)
                        click.echo(
                            click.style(f'Successfully created vector index for app {app.id}.', fg='green'))
                    except Exception as e:
                        click.echo(click.style(f'Failed to created vector index for app {app.id}.', fg='red'))
                        raise e

                click.echo(f'Successfully migrated app annotation {app.id}.')
                create_count += 1  # 更新成功创建索引的app数量
            except Exception as e:
                click.echo(
                    click.style('Create app annotation index error: {} {}'.format(e.__class__.__name__, str(e)),
                                fg='red'))
                continue

    # 迁移完成
    click.echo(
        click.style(f'Congratulations! Create {create_count} app annotation indexes, and skipped {skipped_count} apps.',
                    fg='green'))


def migrate_knowledge_vector_database():
    """
    将知识向量数据库中的数据迁移到目标向量数据库中。
    """
    # 开始迁移向量数据库
    click.echo(click.style('Start migrate vector db.', fg='green'))
    create_count = 0  # 成功创建计数
    skipped_count = 0  # 跳过计数
    total_count = 0  # 总计数
    config = current_app.config  # 应用配置
    vector_type = config.get('VECTOR_STORE')  # 向量存储类型

    page = 1  # 分页起始
    while True:
        try:
            # 查询满足条件的数据集
            datasets = db.session.query(Dataset).filter(Dataset.indexing_technique == 'high_quality') \
                .order_by(Dataset.created_at.desc()).paginate(page=page, per_page=50)
        except NotFound:
            break  # 未找到数据，结束循环

        page += 1  # 分页递增
        for dataset in datasets:
            total_count += 1  # 总计数递增
            # 处理单个数据集
            click.echo(f'Processing the {total_count} dataset {dataset.id}. '
                       + f'{create_count} created, {skipped_count} skipped.')
            try:
                # 创建数据集向量索引
                click.echo('Create dataset vdb index: {}'.format(dataset.id))
                if dataset.index_struct_dict:
                    if dataset.index_struct_dict['type'] == vector_type:
                        skipped_count += 1
                        continue  # 类型匹配，跳过处理

                # 根据向量存储类型设置索引结构
                collection_name = ''
                if vector_type == "weaviate":
                    dataset_id = dataset.id
                    collection_name = Dataset.gen_collection_name_by_id(dataset_id)
                    index_struct_dict = {
                        "type": 'weaviate',
                        "vector_store": {"class_prefix": collection_name}
                    }
                    dataset.index_struct = json.dumps(index_struct_dict)
                elif vector_type == "qdrant":
                    if dataset.collection_binding_id:
                        dataset_collection_binding = db.session.query(DatasetCollectionBinding). \
                            filter(DatasetCollectionBinding.id == dataset.collection_binding_id). \
                            one_or_none()
                        if dataset_collection_binding:
                            collection_name = dataset_collection_binding.collection_name
                        else:
                            raise ValueError('Dataset Collection Bindings is not exist!')
                    else:
                        dataset_id = dataset.id
                        collection_name = Dataset.gen_collection_name_by_id(dataset_id)
                    index_struct_dict = {
                        "type": 'qdrant',
                        "vector_store": {"class_prefix": collection_name}
                    }
                    dataset.index_struct = json.dumps(index_struct_dict)

                elif vector_type == "milvus":
                    dataset_id = dataset.id
                    collection_name = Dataset.gen_collection_name_by_id(dataset_id)
                    index_struct_dict = {
                        "type": 'milvus',
                        "vector_store": {"class_prefix": collection_name}
                    }
                    dataset.index_struct = json.dumps(index_struct_dict)
                else:
                    raise ValueError(f"Vector store {config.get('VECTOR_STORE')} is not supported.")

                # 迁移数据集文档
                vector = Vector(dataset)
                click.echo(f"Start to migrate dataset {dataset.id}.")

                try:
                    vector.delete()  # 删除旧索引
                    click.echo(
                        click.style(f'Successfully delete vector index {collection_name} for dataset {dataset.id}.',
                                    fg='green'))
                except Exception as e:
                    click.echo(
                        click.style(f'Failed to delete vector index {collection_name} for dataset {dataset.id}.',
                                    fg='red'))
                    raise e

                # 处理数据集文档
                dataset_documents = db.session.query(DatasetDocument).filter(
                    DatasetDocument.dataset_id == dataset.id,
                    DatasetDocument.indexing_status == 'completed',
                    DatasetDocument.enabled == True,
                    DatasetDocument.archived == False,
                ).all()

                documents = []
                segments_count = 0
                for dataset_document in dataset_documents:
                    segments = db.session.query(DocumentSegment).filter(
                        DocumentSegment.document_id == dataset_document.id,
                        DocumentSegment.status == 'completed',
                        DocumentSegment.enabled == True
                    ).all()

                    for segment in segments:
                        document = Document(
                            page_content=segment.content,
                            metadata={
                                "doc_id": segment.index_node_id,
                                "doc_hash": segment.index_node_hash,
                                "document_id": segment.document_id,
                                "dataset_id": segment.dataset_id,
                            }
                        )

                        documents.append(document)
                        segments_count += 1

                if documents:
                    try:
                        click.echo(click.style(
                            f'Start to created vector index with {len(documents)} documents of {segments_count} segments for dataset {dataset.id}.',
                            fg='green'))
                        vector.create(documents)  # 创建新索引
                        click.echo(
                            click.style(f'Successfully created vector index for dataset {dataset.id}.', fg='green'))
                    except Exception as e:
                        click.echo(click.style(f'Failed to created vector index for dataset {dataset.id}.', fg='red'))
                        raise e
                # 提交数据库更改
                db.session.add(dataset)
                db.session.commit()
                click.echo(f'Successfully migrated dataset {dataset.id}.')
                create_count += 1
            except Exception as e:
                db.session.rollback()
                click.echo(
                    click.style('Create dataset index error: {} {}'.format(e.__class__.__name__, str(e)),
                                fg='red'))
                continue  # 异常跳过当前数据集

    # 完成迁移
    click.echo(
        click.style(f'Congratulations! Create {create_count} dataset indexes, and skipped {skipped_count} datasets.',
                    fg='green'))


@click.command('convert-to-agent-apps', help='Convert Agent Assistant to Agent App.')
def convert_to_agent_apps():
    """
    Convert Agent Assistant to Agent App.
    """
    click.echo(click.style('Start convert to agent apps.', fg='green'))

    proceeded_app_ids = []

    while True:
        # fetch first 1000 apps
        sql_query = """SELECT a.id AS id FROM apps a
            INNER JOIN app_model_configs am ON a.app_model_config_id=am.id
            WHERE a.mode = 'chat' 
            AND am.agent_mode is not null 
            AND (
				am.agent_mode like '%"strategy": "function_call"%' 
                OR am.agent_mode  like '%"strategy": "react"%'
			) 
            AND (
				am.agent_mode like '{"enabled": true%' 
                OR am.agent_mode like '{"max_iteration": %'
			) ORDER BY a.created_at DESC LIMIT 1000
        """

        with db.engine.begin() as conn:
            rs = conn.execute(db.text(sql_query))

            apps = []
            for i in rs:
                app_id = str(i.id)
                if app_id not in proceeded_app_ids:
                    proceeded_app_ids.append(app_id)
                    app = db.session.query(App).filter(App.id == app_id).first()
                    apps.append(app)

            if len(apps) == 0:
                break

        for app in apps:
            click.echo('Converting app: {}'.format(app.id))

            try:
                app.mode = AppMode.AGENT_CHAT.value
                db.session.commit()

                # update conversation mode to agent
                db.session.query(Conversation).filter(Conversation.app_id == app.id).update(
                    {Conversation.mode: AppMode.AGENT_CHAT.value}
                )

                db.session.commit()
                click.echo(click.style('Converted app: {}'.format(app.id), fg='green'))
            except Exception as e:
                click.echo(
                    click.style('Convert app error: {} {}'.format(e.__class__.__name__,
                                                                  str(e)), fg='red'))

    click.echo(click.style('Congratulations! Converted {} agent apps.'.format(len(proceeded_app_ids)), fg='green'))


def register_commands(app):
    """
    注册应用程序的命令行接口。

    参数:
    - app: 应用程序实例，用于注册命令。

    返回值:
    - 无
    """
    # 为应用程序注册重置密码命令
    app.cli.add_command(reset_password)
    # 为应用程序注册重置电子邮件命令
    app.cli.add_command(reset_email)
    # 为应用程序注册重置加密密钥对命令
    app.cli.add_command(reset_encrypt_key_pair)
    # 为应用程序注册数据库迁移命令
    app.cli.add_command(vdb_migrate)
    app.cli.add_command(convert_to_agent_apps)
