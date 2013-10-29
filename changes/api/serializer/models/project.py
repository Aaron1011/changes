from changes.api.serializer import Serializer, register
from changes.models.project import Project


@register(Project)
class ProjectSerializer(Serializer):
    def serialize(self, instance):
        return {
            'id': instance.id.hex,
            'slug': instance.slug,
            'name': instance.name,
            'dateCreated': instance.date_created,
            'link': '/projects/{0}/'.format(instance.id.hex),
        }
