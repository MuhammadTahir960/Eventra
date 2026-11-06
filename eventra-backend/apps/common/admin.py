class KeepRecordsMixin:
    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ReadOnlyRecordsMixin(KeepRecordsMixin):
    def has_change_permission(self, request, obj=None):
        return False
