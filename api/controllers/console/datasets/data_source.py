import datetime
import json

from flask import request
from flask_login import current_user
from flask_restful import Resource, marshal_with, reqparse
from werkzeug.exceptions import NotFound

from controllers.console import api
from controllers.console.setup import setup_required
from controllers.console.wraps import account_initialization_required
from core.indexing_runner import IndexingRunner
from core.rag.extractor.entity.extract_setting import ExtractSetting
from core.rag.extractor.notion_extractor import NotionExtractor
from extensions.ext_database import db
from fields.data_source_fields import integrate_list_fields, integrate_notion_info_list_fields
from libs.login import login_required
from models.dataset import Document
from models.source import DataSourceOauthBinding
from services.dataset_service import DatasetService, DocumentService
from tasks.document_indexing_sync_task import document_indexing_sync_task


class DataSourceApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(integrate_list_fields)
    def get(self):
        # get workspace data source integrates
        data_source_integrates = (
            db.session.query(DataSourceOauthBinding)
            .filter(
                DataSourceOauthBinding.tenant_id == current_user.current_tenant_id,
                DataSourceOauthBinding.disabled == False,
            )
            .all()
        )

        base_url = request.url_root.rstrip("/")
        data_source_oauth_base_path = "/console/api/oauth/data-source"
        providers = ["notion"]  # 定义支持的数据源提供者列表

        integrate_data = []
        for provider in providers:
            # 遍历提供者列表，为每个提供者构建集成信息
            existing_integrates = filter(lambda item: item.provider == provider, data_source_integrates)
            if existing_integrates:
                # 如果存在已绑定的集成，则构建其信息
                for existing_integrate in list(existing_integrates):
                    integrate_data.append(
                        {
                            "id": existing_integrate.id,
                            "provider": provider,
                            "created_at": existing_integrate.created_at,
                            "is_bound": True,
                            "disabled": existing_integrate.disabled,
                            "source_info": existing_integrate.source_info,
                            "link": f"{base_url}{data_source_oauth_base_path}/{provider}",
                        }
                    )
            else:
                integrate_data.append(
                    {
                        "id": None,
                        "provider": provider,
                        "created_at": None,
                        "source_info": None,
                        "is_bound": False,
                        "disabled": None,
                        "link": f"{base_url}{data_source_oauth_base_path}/{provider}",
                    }
                )
        return {"data": integrate_data}, 200

    @setup_required
    @login_required
    @account_initialization_required
    def patch(self, binding_id, action):
        binding_id = str(binding_id)
        action = str(action)
        data_source_binding = DataSourceOauthBinding.query.filter_by(id=binding_id).first()
        if data_source_binding is None:
            raise NotFound("Data source binding not found.")
        # enable binding
        if action == "enable":
            if data_source_binding.disabled:
                data_source_binding.disabled = False
                data_source_binding.updated_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                db.session.add(data_source_binding)
                db.session.commit()  # 提交数据库事务
            else:
                raise ValueError("Data source is not disabled.")
        # disable binding
        if action == "disable":
            if not data_source_binding.disabled:
                data_source_binding.disabled = True
                data_source_binding.updated_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                db.session.add(data_source_binding)
                db.session.commit()  # 提交数据库事务
            else:
                raise ValueError("Data source is disabled.")
        return {"result": "success"}, 200


class DataSourceNotionListApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(integrate_notion_info_list_fields)
    def get(self):
        dataset_id = request.args.get("dataset_id", default=None, type=str)
        exist_page_ids = []
        
        # 处理已存在的Notion数据源页面
        if dataset_id:
            # 根据数据集ID查询数据集
            dataset = DatasetService.get_dataset(dataset_id)
            if not dataset:
                raise NotFound("Dataset not found.")
            if dataset.data_source_type != "notion_import":
                raise ValueError("Dataset is not notion type.")
            documents = Document.query.filter_by(
                dataset_id=dataset_id,
                tenant_id=current_user.current_tenant_id,
                data_source_type="notion_import",
                enabled=True,
            ).all()
            if documents:
                for document in documents:
                    data_source_info = json.loads(document.data_source_info)
                    exist_page_ids.append(data_source_info["notion_page_id"])
        # get all authorized pages
        data_source_bindings = DataSourceOauthBinding.query.filter_by(
            tenant_id=current_user.current_tenant_id, provider="notion", disabled=False
        ).all()
        if not data_source_bindings:
            return {"notion_info": []}, 200
        pre_import_info_list = []
        for data_source_binding in data_source_bindings:
            source_info = data_source_binding.source_info
            pages = source_info["pages"]
            # Filter out already bound pages
            for page in pages:
                if page["page_id"] in exist_page_ids:
                    page["is_bound"] = True
                else:
                    page["is_bound"] = False
            pre_import_info = {
                "workspace_name": source_info["workspace_name"],
                "workspace_icon": source_info["workspace_icon"],
                "workspace_id": source_info["workspace_id"],
                "pages": pages,
            }
            pre_import_info_list.append(pre_import_info)
        return {"notion_info": pre_import_info_list}, 200


class DataSourceNotionApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def get(self, workspace_id, page_id, page_type):
        """
        根据给定的工作空间ID、页面ID和页面类型，从Notion中提取文本文档的内容。

        参数:
        - workspace_id: 工作空间的ID，将被转换为字符串格式。
        - page_id: 页面的ID，将被转换为字符串格式。
        - page_type: 页面的类型。

        返回值:
        - 一个包含页面内容的字典，以及HTTP状态码200。
        
        抛出:
        - NotFound: 如果找不到对应的数据源绑定时抛出。
        """

        # 将输入的ID转换为字符串格式
        workspace_id = str(workspace_id)
        page_id = str(page_id)
        data_source_binding = DataSourceOauthBinding.query.filter(
            db.and_(
                DataSourceOauthBinding.tenant_id == current_user.current_tenant_id,
                DataSourceOauthBinding.provider == "notion",
                DataSourceOauthBinding.disabled == False,
                DataSourceOauthBinding.source_info["workspace_id"] == f'"{workspace_id}"',
            )
        ).first()
        
        # 如果找不到对应的数据源绑定，抛出未找到异常
        if not data_source_binding:
            raise NotFound("Data source binding not found.")

        # 初始化NotionExtractor以提取内容
        extractor = NotionExtractor(
            notion_workspace_id=workspace_id,
            notion_obj_id=page_id,
            notion_page_type=page_type,
            notion_access_token=data_source_binding.access_token,
            tenant_id=current_user.current_tenant_id,
        )

        # 提取文本文档
        text_docs = extractor.extract()
        return {"content": "\n".join([doc.page_content for doc in text_docs])}, 200

    @setup_required
    @login_required
    @account_initialization_required
    def post(self):
        """
        处理POST请求，用于从Notion中提取信息并进行文档处理和索引的估计。

        参数:
        - notion_info_list: Notion信息列表，包含workspace_id和pages信息，必需。
        - process_rule: 处理规则字典，定义如何处理和索引文档，必需。
        - doc_form: 文档形式，默认为'text_model'，非必需。
        - doc_language: 文档语言，默认为'English'，非必需。

        返回值:
        - response: 执行估计操作后的响应数据，通常包含估计结果或错误信息。
        - 200: HTTP状态码，表示请求成功处理。
        """
        parser = reqparse.RequestParser()
        parser.add_argument("notion_info_list", type=list, required=True, nullable=True, location="json")
        parser.add_argument("process_rule", type=dict, required=True, nullable=True, location="json")
        parser.add_argument("doc_form", type=str, default="text_model", required=False, nullable=False, location="json")
        parser.add_argument(
            "doc_language", type=str, default="English", required=False, nullable=False, location="json"
        )
        args = parser.parse_args()
        # 验证参数的合法性
        DocumentService.estimate_args_validate(args)
        notion_info_list = args["notion_info_list"]
        extract_settings = []
        # 遍历Notion信息列表，为每个页面创建提取设置
        for notion_info in notion_info_list:
            workspace_id = notion_info["workspace_id"]
            for page in notion_info["pages"]:
                extract_setting = ExtractSetting(
                    datasource_type="notion_import",
                    notion_info={
                        "notion_workspace_id": workspace_id,
                        "notion_obj_id": page["page_id"],
                        "notion_page_type": page["type"],
                        "tenant_id": current_user.current_tenant_id,
                    },
                    document_model=args["doc_form"],
                )
                extract_settings.append(extract_setting)
        # 初始化索引运行器，并执行索引估计操作
        indexing_runner = IndexingRunner()
        response = indexing_runner.indexing_estimate(
            current_user.current_tenant_id,
            extract_settings,
            args["process_rule"],
            args["doc_form"],
            args["doc_language"],
        )
        return response, 200


class DataSourceNotionDatasetSyncApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def get(self, dataset_id):
        """
        获取并同步指定数据集的所有文档。

        参数:
        - dataset_id: 数据集的ID，类型为int或能够被转换为str的值。

        返回值:
        - 200: 请求成功，数据集文档开始同步。
        - NotFound: 数据集不存在时抛出的异常。
        """
        dataset_id_str = str(dataset_id)  # 将dataset_id转换为字符串
        dataset = DatasetService.get_dataset(dataset_id_str)  # 根据ID获取数据集
        if dataset is None:  # 数据集不存在时抛出异常
            raise NotFound("Dataset not found.")

        documents = DocumentService.get_document_by_dataset_id(dataset_id_str)  # 根据数据集ID获取所有文档
        for document in documents:  # 遍历文档列表，为每个文档安排同步任务
            document_indexing_sync_task.delay(dataset_id_str, document.id)
        return 200  # 请求成功，返回200状态码


class DataSourceNotionDocumentSyncApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def get(self, dataset_id, document_id):
        """
        同步指定的数据集ID和文档ID对应的Notion文档。
        
        Parameters:
            dataset_id (int): 数据集的ID。
            document_id (int): 文档的ID。
            
        Returns:
            int: 请求处理成功返回200。
            
        Raises:
            NotFound: 如果指定的数据集或文档不存在时抛出。
        """
        # 将传入的ID转换为字符串格式
        dataset_id_str = str(dataset_id)
        document_id_str = str(document_id)
        
        # 获取指定ID的数据集
        dataset = DatasetService.get_dataset(dataset_id_str)
        if dataset is None:
            raise NotFound("Dataset not found.")  # 如果数据集不存在，抛出异常
        
        # 获取指定数据集和文档ID的文档
        document = DocumentService.get_document(dataset_id_str, document_id_str)
        if document is None:
            raise NotFound("Document not found.")  # 如果文档不存在，抛出异常
        
        # 异步执行文档索引同步任务
        document_indexing_sync_task.delay(dataset_id_str, document_id_str)
        
        return 200  # 请求处理成功，返回200


api.add_resource(DataSourceApi, "/data-source/integrates", "/data-source/integrates/<uuid:binding_id>/<string:action>")
api.add_resource(DataSourceNotionListApi, "/notion/pre-import/pages")
api.add_resource(
    DataSourceNotionApi,
    "/notion/workspaces/<uuid:workspace_id>/pages/<uuid:page_id>/<string:page_type>/preview",
    "/datasets/notion-indexing-estimate",
)
api.add_resource(DataSourceNotionDatasetSyncApi, "/datasets/<uuid:dataset_id>/notion/sync")
api.add_resource(
    DataSourceNotionDocumentSyncApi, "/datasets/<uuid:dataset_id>/documents/<uuid:document_id>/notion/sync"
)
