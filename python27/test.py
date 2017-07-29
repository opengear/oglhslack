#import dynamic_oglh_client
#client = dynamic_oglh_client.LighthouseApiClient()
#client = client.get_client()
#print(client.nodes.list(per_page=1, page=3))
#print(client.nodes.get('nodes_tags-51'))

import lhapi
client = lhapi.LighthouseApiClient()
#print(client.nodes().list(per_page=1, page=3))
print(client.nodes().find('nodes_tags-51'))
#print(client.nodes().list(per_page=1, page=3))
#for node in body['nodes']:
#    if node['approved'] == 0:
#        print node['id']
