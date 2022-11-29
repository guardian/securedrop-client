from securedrop_client.storage import get_local_sources, get_local_messages, get_local_replies



def get_source(session):
    sources = get_local_sources(session)
    messages = get_local_messages(session)
    replies = get_local_replies(session)


    for source in sources:
        print(source.id)
