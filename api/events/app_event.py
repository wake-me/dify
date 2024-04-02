from blinker import signal

# 定义一个名为'app-was-created'的信号，发送者为app
app_was_created = signal('app-was-created')

# 定义一个名为'app-was-deleted'的信号，发送者为app
app_was_deleted = signal('app-was-deleted')

# 定义一个名为'app-model-config-was-updated'的信号，发送者为app，
# 参数包括旧的应用模型配置和新的应用模型配置
app_model_config_was_updated = signal('app-model-config-was-updated')