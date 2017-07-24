import lhapi
client = lhapi.LighthouseApiClient()
#client._do_auth()
print(client.nodes().manifest())
