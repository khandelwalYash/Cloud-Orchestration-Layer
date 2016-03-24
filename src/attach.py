def getXML(imageName, host, pool, dev):
	xml = """<disk type='block' device='disk'>
				<driver name='qemu' type='raw'/>
				<source protocol='rbd' dev='/dev/rbd/%s/%s'>
					 <host name='%s' port='6789'/>
				</source>
				<target dev='%s' bus='virtio'/>
				<address type='pci' domain='0x0000' bus='0x00' slot='0x05' function='0x0'/>
			</disk>"""%(pool, imageName, host, dev)
	return xml
