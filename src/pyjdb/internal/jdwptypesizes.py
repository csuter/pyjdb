def JdwpTypes():
  return [
      'byte',
      'boolean',
      'int',
      'long',
      'objectID',
      'tagged-objectID',
      'threadID',
      'threadGroupID',
      'stringID',
      'classLoaderID',
      'classObjectID',
      'arrayID',
      'referenceTypeID',
      'classID',
      'interfaceID',
      'arrayTypeID',
      'methodID',
      'fieldID',
      'frameID'
  ]

def JdwpTypeSize(jdwp_type, id_sizes):
  if id_sizes is None:
    return {
      'byte' : 1,
      'boolean' : 1,
      'int' : 4,
      'long' : 8
    }[jdwp_type]
  return {
      'byte' : 1,
      'boolean' : 1,
      'int' : 4,
      'long' : 8,
      'objectID' : id_sizes['objectIDSize'],
      'tagged-objectID' : 1+id_sizes['objectIDSize'],
      'threadID' : id_sizes['objectIDSize'],
      'threadGroupID' : id_sizes['objectIDSize'],
      'stringID' : id_sizes['objectIDSize'],
      'classLoaderID' : id_sizes['objectIDSize'],
      'classObjectID' : id_sizes['objectIDSize'],
      'arrayID' : id_sizes['objectIDSize'],
      'referenceTypeID' : id_sizes['referenceTypeIDSize'],
      'classID' : id_sizes['referenceTypeIDSize'],
      'interfaceID' : id_sizes['referenceTypeIDSize'],
      'arrayTypeID' : id_sizes['referenceTypeIDSize'],
      'methodID' : id_sizes['methodIDSize'],
      'fieldID' : id_sizes['fieldIDSize'],
      'frameID' : id_sizes['frameIDSize'],
    }[jdwp_type]
