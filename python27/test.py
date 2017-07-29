import dynamic_oglh_client
client = dynamic_oglh_client.LighthouseApiClient()
client = client.get_client()

print(client.system.time.get())
#print(client.services.https.get())
#print(client.nodes.list())
#print(client.nodes.list(per_page=1, page=3))
#print(client.nodes.ids.get())
#print(client.nodes.fields.get())
#print(client.nodes.tags.get(id='nodes-13', tag_value_id='London'))
#print(client.nodes.tags.list(id='nodes-13'))
#print(client.nodes.registration_package.get(id='nodes-13'))
#print(client.nodes.manifest.get())
#print(client.nodes.list(per_page=1, page=3))
#print(client.nodes.get(id='nodes-13'))
#print(client.nodes.smartgroups.get(groupId='smart_groups_nodes_groups-2'))

#import lhapi
#client = lhapi.LighthouseApiClient()
#print(client.nodes().smartgroups().find('smart_groups_nodes_groups-2'))
#print(client.nodes().list(per_page=1, page=3))
#print(client.nodes().find('nodes_tags-51'))
#print(client.nodes().list(per_page=1, page=3))
#for node in body['nodes']:
#    if node['approved'] == 0:
#        print node['id']
