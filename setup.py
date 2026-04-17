from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

setup(
    name="erpnext_stripe",
    version="1.0.0",
    description="Stripe Payments for ERPNext — multi-company, PCI-compliant, marketplace-ready",
    author="IPCONNEX",
    author_email="dev@ipconnex.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
