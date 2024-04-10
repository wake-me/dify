from core.app.app_config.entities import VariableEntity
from models.workflow import Workflow


class WorkflowVariablesConfigManager:
    @classmethod
    def convert(cls, workflow: Workflow) -> list[VariableEntity]:
        """
        将工作流启动变量转换为变量实体列表

        :param workflow: 工作流实例
        :return: 变量实体列表
        """
        variables = []

        # 查找起始节点
        user_input_form = workflow.user_input_form()

        # 遍历用户输入表单，创建变量实体列表
        for variable in user_input_form:
            variables.append(VariableEntity(**variable))

        return variables