from tortoise import fields, models

class User(models.Model):
    id = fields.IntField(pk=True)
    qq_id = fields.CharField(max_length=20)
    group_id = fields.CharField(max_length=20)
    name = fields.CharField(max_length=100)
    # 新增：成员标签
    tags = fields.JSONField(default=list)

    class Meta:
        table = "trans_users"
        unique_together = (("qq_id", "group_id"),)

class Project(models.Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=100, unique=True)
    aliases = fields.JSONField(default=list)
    # 新增：项目标签
    tags = fields.JSONField(default=list)

    group_id = fields.CharField(max_length=20)
    group_name = fields.CharField(max_length=100, null=True)

    leader = fields.ForeignKeyField('models.User', related_name='led_projects', null=True)

    default_translator = fields.ForeignKeyField('models.User', related_name='def_trans_projects', null=True)
    default_proofreader = fields.ForeignKeyField('models.User', related_name='def_proof_projects', null=True)
    default_typesetter = fields.ForeignKeyField('models.User', related_name='def_type_projects', null=True)

    class Meta:
        table = "trans_projects"

class Episode(models.Model):
    id = fields.IntField(pk=True)
    project = fields.ForeignKeyField('models.Project', related_name='episodes')
    title = fields.CharField(max_length=50)
    status = fields.IntField(default=0) # 0:未开始, 1:翻译, 2:校对, 3:嵌字, 4:完结

    translator = fields.ForeignKeyField('models.User', related_name='tasks_trans', null=True)
    proofreader = fields.ForeignKeyField('models.User', related_name='tasks_proof', null=True)
    typesetter = fields.ForeignKeyField('models.User', related_name='tasks_type', null=True)

    ddl_trans = fields.DatetimeField(null=True)
    ddl_proof = fields.DatetimeField(null=True)
    ddl_type = fields.DatetimeField(null=True)

    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "trans_episodes"
        unique_together = (("project", "title"),)

class GroupSetting(models.Model):
    group_id = fields.CharField(max_length=20, pk=True)
    enable_broadcast = fields.BooleanField(default=True) # 默认开启播报
    broadcast_time = fields.CharField(max_length=20, default="10:00") # 新增：播报时间，格式如 "10:00"

    class Meta:
        table = "trans_group_settings"
